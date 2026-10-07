"""Activity per cycle for the BotEngine.

Cada ciclo o bot engine chama este módulo para gerar atividade no order book.
Estrutura: 10 lotes × 120 bots = 1200 bots totais.
"""

from __future__ import annotations

import asyncio
from random import uniform, randint
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.commodity import Commodity as CommodityModel
from app.models.order import Order as OrderModel  # type: ignore  # evitar import circular no nível de topo; ajustar se necessário


class BotActivity:
    """Gera ordens de bot a cada ciclo do engine."""

    def __init__(self):
        self.snapshot_data: dict | None = None

    async def cycle(self, order_book: Any) -> None:
        """Insere ordens no order book como se fossem bots."""
        sess = SessionLocal()
        try:
            # Congeladas (suspenso pelo admin) não recebem ordem nova
            commodities = (
                sess.query(CommodityModel)
                .filter(CommodityModel.is_frozen.is_(False))
                .all()
            )
            if not commodities:
                return
            # Insere 1 ordem por lote este ciclo (10 ordens totais por ciclo)
            for _ in range(getattr(settings, "bots_lotes", 10)):
                c = commodities[randint(0, len(commodities) - 1)]
                # 50/50: book de um lado só empurra o preço pra bolha
                # (mais compradores que vendedores = preço sobe sem parar)
                side = "bid" if uniform(0, 1) > 0.5 else "ask"
                base = c.current_price or c.base_price
                price = max(base + uniform(-base * 0.1, base * 0.1), 0.01)
                qty = uniform(0.1, 5.0)

                order = OrderModel(
                    commodity_id=c.id,
                    user_id=None,  # order from system/bot
                    side=side,
                    quantity=round(qty, 2),
                    executed_quantity=0.0,
                    price=round(price, 2),
                    filled=False,
                )
                # Insere no order book compartilhado
                if hasattr(order_book, "add"):
                    order_book.add(order)
                # Persiste no banco
                sess.add(order)
            sess.commit()
        except Exception:
            sess.rollback()
        finally:
            sess.close()

    def snapshot(self) -> dict | None:
        """Retorna dados para broadcast via WebSocket."""
        # Placeholder: poderia retornar contagens, preços melhores etc.
        return {
            "bots_active": getattr(settings, "bots_total", 1200),
            "lotes": getattr(settings, "bots_lotes", 10),
        }