from __future__ import annotations

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.market.engine import faixa_preco, limita_preco, preco_vivo
from app.core.market.orderbook import order_book
from app.core.market.prune import prune_orders
from app.models.commodity import Commodity
from app.models.order import Order
from app.models.price_tick import PriceTick
from app.schemas.commodity import (
    ClearBookIn,
    CommodityCreate,
    CommodityFreeze,
    CommodityOut,
    CommodityShock,
    CommodityUpdate,
    PricePointOut,
)


class CommodityController:
    """Camada de controle: CRUD de commodities (apenas admin)."""

    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[CommodityOut]:
        rows = self.db.query(Commodity).order_by(Commodity.name.asc()).all()
        return [CommodityOut.model_validate(r) for r in rows]

    def get(self, commodity_id: int) -> CommodityOut:
        return CommodityOut.model_validate(self._row(commodity_id))

    def _row(self, commodity_id: int) -> Commodity:
        row = self.db.get(Commodity, commodity_id)
        if row is None:
            raise NotFoundError(f"Commodity {commodity_id} não encontrada")
        return row

    # --- intervenções do admin -----------------------------------------

    def _persist_prices(self, alteradas: list[tuple[int, float]]) -> None:
        """Joga pro banco os preços que o book já mudou em memória."""
        for oid, preco in alteradas:
            self.db.execute(
                update(Order).where(Order.id == oid).values(price=preco)
            )

    def _refresh_display(self, c: Commodity, *, manter_atual: bool = False) -> None:
        """Recalcula o preço exibido do book agora (não espera o tick do
        engine) e deixa uma amostra no gráfico — o admin vê o efeito na hora."""
        base = float(c.base_price or 0)
        preco = preco_vivo(
            order_book.best_bid_price(c.id),
            order_book.best_ask_price(c.id),
            base,
        )
        if preco is None:
            if not manter_atual:
                return
            preco = limita_preco(float(c.current_price or base), base)
        c.current_price = preco
        if base:
            c.variation_24h = round((preco - base) / base * 100, 2)
        self.db.add(PriceTick(commodity_id=c.id, price=preco))

    def shock(self, commodity_id: int, payload: CommodityShock) -> dict:
        """Choque de preço: move todas as ordens abertas em ±percent.

        O book inteiro anda junto (recortado na faixa nominal), as ordens
        cruzadas executam na hora e o preço exibido acompanha no mesmo
        segundo — é o "empurrão" do admin no mercado.
        """
        c = self._row(commodity_id)
        base = float(c.base_price or 0)
        floor, ceil = faixa_preco(base) if base > 0 else (0.01, None)
        alteradas = order_book.shock_prices(
            c.id, 1 + payload.percent / 100, floor, ceil
        )
        self._persist_prices(alteradas)
        self._refresh_display(c)
        self.db.commit()
        return {
            "detail": (
                f"{c.name}: choque de {payload.percent:+.0f}% — "
                f"{len(alteradas)} ordens reprecificadas"
            ),
            "ordens_movidas": len(alteradas),
            "preco": float(c.current_price or 0),
        }

    def set_base_price(
        self, commodity_id: int, payload: CommodityUpdate
    ) -> CommodityOut:
        """Troca o preço base (a âncora nominal) e recorta o book na nova
        faixa — o mercado inteiro reage pro novo nominal na hora."""
        c = self._row(commodity_id)
        c.base_price = round(float(payload.base_price), 2)
        lo, hi = faixa_preco(c.base_price)
        # factor 1.0 = não empurra, só corta o que ficou fora da faixa nova
        self._persist_prices(order_book.shock_prices(c.id, 1.0, lo, hi))
        self._refresh_display(c, manter_atual=True)
        self.db.commit()
        self.db.refresh(c)
        return CommodityOut.model_validate(c)

    def set_frozen(
        self, commodity_id: int, payload: CommodityFreeze
    ) -> CommodityOut:
        """Congela/reabre: congelada não aceita ordem nova (jogador nem bot);
        as ordens repousantes ficam paradas até o admin reabrir."""
        c = self._row(commodity_id)
        c.is_frozen = bool(payload.frozen)
        self.db.commit()
        self.db.refresh(c)
        return CommodityOut.model_validate(c)

    def clear_book(
        self, commodity_id: int, payload: ClearBookIn | None = None
    ) -> dict:
        """Emergência por commodity: cancela todas as ordens abertas (livres
        de qualquer execução, então ninguém perde dinheiro) e, por padrão,
        devolve o preço ao nominal. Os bots reabastecem o book em ~100ms."""
        resetar = True if payload is None else bool(payload.reset_price)
        c = self._row(commodity_id)
        removidas = self.db.execute(
            text(
                "DELETE FROM orders "
                "WHERE filled = false AND commodity_id = :cid "
                "RETURNING id"
            ),
            {"cid": c.id},
        ).fetchall()
        ids = {r[0] for r in removidas}
        if ids:
            order_book.remove_ids(ids)
        if resetar:
            c.current_price = c.base_price
            c.variation_24h = 0.0
            self.db.add(
                PriceTick(commodity_id=c.id, price=float(c.base_price or 0))
            )
        self.db.commit()
        return {
            "detail": f"{c.name}: {len(ids)} ordens canceladas",
            "ordens_canceladas": len(ids),
            "preco": float(c.current_price or 0),
        }

    def reset_market(self) -> dict:
        """Zerada geral: sai tudo que está aberto e os preços voltam ao
        nominal. Os ticks ficam — o gráfico mostra a queda do reset."""
        stats = prune_orders(order_book, limpar_abertas=True)
        resetadas = 0
        for c in self.db.query(Commodity).all():
            c.current_price = c.base_price
            c.variation_24h = 0.0
            self.db.add(
                PriceTick(commodity_id=c.id, price=float(c.base_price or 0))
            )
            resetadas += 1
        self.db.commit()
        return {
            "detail": "Mercado zerado: book limpo e preços no nominal",
            "ordens_canceladas": int(stats.get("abertas_expiradas", 0)),
            "commodities_resetadas": resetadas,
        }

    def create(self, payload: CommodityCreate) -> CommodityOut:
        exists = self.db.query(Commodity).filter(Commodity.name == payload.name).first()
        if exists:
            raise ConflictError(f"Commodity '{payload.name}' já existe")
        commodity = Commodity(
            name=payload.name,
            description=payload.description,
            base_price=payload.base_price,
            current_price=payload.base_price,
        )
        self.db.add(commodity)
        self.db.commit()
        self.db.refresh(commodity)
        return CommodityOut.model_validate(commodity)

    def seed_defaults(self) -> None:
        """Semente 5 commodities padrão dos anos 1920 se não existirem."""
        defaults = [
            {"name": "Carvão", "description": "Carvão mineral", "base_price": 50.0},
            {"name": "Aço", "description": "Lamina de aço", "base_price": 120.0},
            {"name": "Trigo", "description": "Trigo em grãos", "base_price": 200.0},
            {"name": "Algodão", "description": "Algodão cru", "base_price": 80.0},
            {"name": "Café", "description": "Café em grãos", "base_price": 150.0},
        ]
        for d in defaults:
            exists = self.db.query(Commodity).filter(Commodity.name == d["name"]).first()
            if not exists:
                c = Commodity(
                    name=d["name"],
                    description=d["description"],
                    base_price=d["base_price"],
                    current_price=d["base_price"],
                )
                self.db.add(c)
        self.db.commit()

    def refresh_prices(self) -> None:
        """Atualiza current_price baseando-se na variação (para ser chamado pelo engine)."""
        rows = self.db.query(Commodity).all()
        for r in rows:
            # Lógica simples: current_price já reflete variação; aqui apenas reset placeholder
            r.current_price = r.base_price + r.variation_24h
        self.db.commit()

    def history(self, limit: int = 180) -> list[PricePointOut]:
        """Últimas `limit` amostras de preço de cada commodity (janela do gráfico)."""
        rows = self.db.execute(
            text(
                """
                SELECT commodity_id, price, created_at
                FROM (
                    SELECT commodity_id, price, created_at,
                           row_number() OVER (
                               PARTITION BY commodity_id ORDER BY id DESC
                           ) AS rn
                    FROM price_ticks
                ) ranked
                WHERE rn <= :limit
                ORDER BY commodity_id, created_at
                """
            ),
            {"limit": limit},
        ).fetchall()
        return [
            PricePointOut(commodity_id=r[0], price=r[1], created_at=r[2])
            for r in rows
        ]