from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.market.estoque import bump_position
from app.core.market.produtoras import _dt, produtoras
from app.models.commodity import Commodity
from app.models.position import Position
from app.models.produtora import Producer
from app.models.user import User
from app.schemas.produtoras import ProdutoraComprar, ProdutoraOut, ProdutoraProduzir


class ProdutorasController:
    """Clicker de estoque: comprar produtora, produzir por clique, melhorar.

    Todas as escritas sob lock na ORDEM user → producer (mesma ordem da
    varredura de manutenção) — dois cliques concorrentes não passam
    checando o mesmo saldo/energia, e o lock só libera no commit.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- estado --

    def estado(self, user_id: int) -> dict:
        """GET /api/produtoras — catálogo das commodities + minhas."""
        produtoras._checar_arquivo()
        cfg = produtoras.cfg
        commodities = self.db.query(Commodity).order_by(Commodity.id).all()
        minhas = {
            p.commodity_id: p
            for p in self.db.query(Producer).filter(Producer.user_id == user_id).all()
        }

        catalogo: list[dict] = []
        saida: list[ProdutoraOut] = []
        for com in commodities:
            d = produtoras.def_da_commodity(com)
            catalogo.append(
                {
                    "commodity_id": com.id,
                    "name": com.name,
                    "emoji": d["emoji"],
                    "nome": d["nome"],
                    "custo_compra": d["custo_compra"],
                    "congelada": bool(com.is_frozen),
                    "base_price": float(com.base_price or 0),
                    "ja_tem": com.id in minhas,
                }
            )
            p = minhas.get(com.id)
            if p is not None:
                saida.append(self._out(p, com, d))

        return {
            "config": {
                "dia_segundos": cfg["dia_segundos"],
                "energia_max": cfg["energia_max"],
                "energia_por_clique": cfg["energia_por_clique"],
                "energia_regen_por_segundo": cfg["energia_regen_por_segundo"],
                "cooldown_segundos": cfg["cooldown_segundos"],
                "insumo_fracao": cfg["insumo_fracao"],
                "lote_nivel_fator": cfg["lote_nivel_fator"],
                "cap_nivel_fator": cfg["cap_nivel_fator"],
                "manutencao_fracao": cfg["manutencao_fracao"],
                "nivel_max": cfg["nivel_max"],
                "jackpot_chance": cfg["jackpot_chance"],
                "jackpot_fator": cfg["jackpot_fator"],
            },
            "catalogo": catalogo,
            "minhas": saida,
        }

    # ------------------------------------------------------------- compra --

    def comprar(self, user_id: int, payload: ProdutoraComprar) -> ProdutoraOut:
        """POST /api/produtoras/comprar — uma produtora por commodity."""
        produtoras._checar_arquivo()
        user = (
            self.db.query(User).filter(User.id == user_id).with_for_update().first()
        )
        if user is None:
            raise NotFoundError("Usuário não encontrado")
        com = (
            self.db.query(Commodity).filter(Commodity.id == payload.commodity_id).first()
        )
        if com is None:
            raise NotFoundError(f"Commodity #{payload.commodity_id} não existe")
        if com.is_frozen:
            raise ConflictError(f"{com.name} está congelada pelo admin — compre depois")

        existe = (
            self.db.query(Producer)
            .filter(Producer.user_id == user_id)
            .filter(Producer.commodity_id == com.id)
            .first()
        )
        if existe is not None:
            raise ConflictError(f"Você já tem a produtora de {com.name}")

        d = produtoras.def_da_commodity(com)
        custo = float(d["custo_compra"])
        if float(user.balance or 0) < custo - 1e-9:
            raise ConflictError(f"{d['nome']} custa {custo:.2f} — saldo insuficiente")

        user.balance = round(float(user.balance or 0) - custo, 2)
        agora = datetime.now(timezone.utc)
        p = Producer(
            user_id=user_id,
            commodity_id=com.id,
            nivel=1,
            energia=float(produtoras.cfg["energia_max"]),
            energia_em=agora,
            ciclo_em=agora,
        )
        self.db.add(p)
        try:
            self.db.commit()
        except IntegrityError:
            # Corrida: dois requests simultâneos comprando a mesma commodity.
            self.db.rollback()
            raise ConflictError(f"Você já tem a produtora de {com.name}")
        self.db.refresh(p)
        return self._out(p, com, d)

    # ---------------------------------------------------------- produção --

    def produzir(self, user_id: int, producer_id: int) -> ProdutoraProduzir:
        """POST /api/produtoras/{id}/produzir — um clique = um lote."""
        produtoras._checar_arquivo()
        cfg = produtoras.cfg
        user, p = self._travar(user_id, producer_id)
        com = self.db.get(Commodity, p.commodity_id)
        if com is None:
            raise NotFoundError("Commodity da produtora não existe mais")
        if com.is_frozen:
            raise ConflictError(f"{com.name} está congelada pelo admin — sem produção")

        # Dia vencido: cobra manutenção (e pode parar a produtora) ANTES do clique.
        produtoras._rolar_dia(self.db, user, p)
        if not p.ativa:
            self.db.commit()  # persiste a parada/quitação mesmo sem produzir
            raise ConflictError(
                f"{produtoras.def_da_commodity(com)['nome']} está parada: dívida "
                f"de {p.divida:.2f}. Espere o saldo cobrir — a dívida paga "
                "sozinha na próxima varredura."
            )

        agora = datetime.now(timezone.utc)
        # Cooldown servidor (anti-macro): a UI só espelha este número.
        ultimo = _dt(p.ultimo_clique_em)
        if ultimo is not None:
            falta = (ultimo + timedelta(seconds=cfg["cooldown_segundos"])) - agora
            if falta.total_seconds() > 0:
                self.db.commit()  # persiste a rolagem de dia feita acima
                raise ConflictError("Descansando… clique mais devagar")

        # Energia: regeneração lazily compensada na leitura.
        energia = self._energia(p, agora)
        if energia < cfg["energia_por_clique"] - 1e-9:
            self.db.commit()  # persiste a rolagem de dia feita acima
            raise ConflictError("Sem energia — espere recarregar")

        cap = produtoras.cap_diario(p.nivel)
        if p.producao_dia >= cap - 1e-9:
            self.db.commit()  # persiste a rolagem de dia feita acima
            raise ConflictError(
                f"Cap diário atingido ({cap:.0f} un) — o dia de jogo vira em "
                f"{max(0, self._dia_vence_em(p, agora) - time.time()):.0f}s"
            )

        base = float(com.base_price or 0)
        if base <= 0:
            self.db.commit()  # persiste a rolagem de dia feita acima
            raise ConflictError(
                f"{com.name} sem preço nominal — sem insumo calculável"
            )

        # Sorteia o lote e cobra o insumo — sem saldo pra insumo, sem clique.
        unidades, jackpot = produtoras.rolar_lote(p.nivel)
        custo_insumo = produtoras.custo_insumo(unidades, base)
        if float(user.balance or 0) < custo_insumo - 1e-9:
            self.db.commit()  # persiste a rolagem de dia feita acima
            raise ConflictError(
                f"Insumo do lote custa {custo_insumo:.2f} — "
                f"saldo {float(user.balance or 0):.2f} insuficiente"
            )

        # Débito do insumo + crédito do estoque (preço médio = custo unitário
        # do insumo: o P&L da carteira continua honesto).
        user.balance = round(float(user.balance or 0) - custo_insumo, 2)
        preco_unitario = round(custo_insumo / unidades, 6) if unidades else base
        bump_position(self.db, user_id, com.id, unidades, preco_unitario)

        p.energia = round(energia - cfg["energia_por_clique"], 4)
        p.energia_em = agora
        p.ultimo_clique_em = agora
        p.producao_dia = round(p.producao_dia + unidades, 6)
        self.db.commit()

        pos = (
            self.db.query(Position)
            .filter(Position.user_id == user_id)
            .filter(Position.commodity_id == com.id)
            .first()
        )
        d = produtoras.def_da_commodity(com)
        return ProdutoraProduzir(
            produzida=self._out(p, com, d),
            unidades=unidades,
            jackpot=jackpot,
            custo_insumo=custo_insumo,
            saldo=float(user.balance or 0),
            posicao_quantidade=float(pos.quantity if pos else unidades),
        )

    # ----------------------------------------------------------- melhoria --

    def melhorar(self, user_id: int, producer_id: int) -> ProdutoraOut:
        """POST /api/produtoras/{id}/melhorar — nível 1..N (custo escalonado)."""
        produtoras._checar_arquivo()
        cfg = produtoras.cfg
        user, p = self._travar(user_id, producer_id)
        com = self.db.get(Commodity, p.commodity_id)
        if com is None:
            raise NotFoundError("Commodity da produtora não existe mais")
        if p.nivel >= cfg["nivel_max"]:
            raise ConflictError(f"Já está no nível máximo ({cfg['nivel_max']:.0f})")
        d = produtoras.def_da_commodity(com)
        custo = produtoras.custo_melhoria(float(d["custo_compra"]), p.nivel)
        if float(user.balance or 0) < custo - 1e-9:
            raise ConflictError(
                f"Melhoria para o nível {p.nivel + 1} custa {custo:.2f}"
            )

        user.balance = round(float(user.balance or 0) - custo, 2)
        p.nivel += 1
        self.db.commit()
        return self._out(p, com, d)

    # ------------------------------------------------------------- helper --

    def _travar(self, user_id: int, producer_id: int) -> tuple[User, Producer]:
        """Trava user e producer na ORDEM fixa user → producer (sem deadlock)."""
        user = (
            self.db.query(User).filter(User.id == user_id).with_for_update().first()
        )
        if user is None:
            raise NotFoundError("Usuário não encontrado")
        p = (
            self.db.query(Producer)
            .filter(Producer.id == producer_id)
            .filter(Producer.user_id == user_id)
            .with_for_update()
            .first()
        )
        if p is None:
            raise NotFoundError("Produtora não encontrada")
        return user, p

    @staticmethod
    def _energia(p: Producer, agora: datetime) -> float:
        """Energia corrente compensando a regeneração desde a última sync."""
        cfg = produtoras.cfg
        desde = (_dt(p.energia_em) or agora).timestamp()
        decorrido = max(0.0, agora.timestamp() - desde)
        return min(
            cfg["energia_max"],
            float(p.energia or 0) + decorrido * cfg["energia_regen_por_segundo"],
        )

    @staticmethod
    def _dia_vence_em(p: Producer, agora: datetime) -> float:
        """Epoch do próximo fim de dia de jogo (cap zera + manutenção)."""
        inicio = (_dt(p.ciclo_em) or agora).timestamp()
        dia = produtoras.cfg["dia_segundos"]
        elapsed = max(0.0, agora.timestamp() - inicio)
        return inicio + (int(elapsed // dia) + 1) * dia

    def _out(self, p: Producer, com: Commodity, d: dict) -> ProdutoraOut:
        """Serializa uma produtora com todos os números que a UI precisa."""
        cfg = produtoras.cfg
        agora = datetime.now(timezone.utc)
        energia = self._energia(p, agora)
        lo, hi = produtoras.lote(p.nivel)
        base = float(com.base_price or 0)
        custo_unit = round(base * cfg["insumo_fracao"], 4)
        nivel_max = int(cfg["nivel_max"])
        custo_melhoria = (
            None
            if p.nivel >= nivel_max
            else produtoras.custo_melhoria(float(d["custo_compra"]), p.nivel)
        )

        # Próxima energia (epoch) e fim do cooldown (epoch) — UI sem drift.
        prox_energia = None
        if energia < cfg["energia_max"] - 1e-9:
            falta = (cfg["energia_max"] - energia) / cfg["energia_regen_por_segundo"]
            prox_energia = time.time() + falta
        ultimo = _dt(p.ultimo_clique_em)
        prox_clique = None
        if ultimo is not None:
            fim = ultimo + timedelta(seconds=cfg["cooldown_segundos"])
            if fim > agora:
                prox_clique = fim.timestamp()

        return ProdutoraOut(
            id=p.id,
            commodity_id=com.id,
            name=com.name,
            emoji=d["emoji"],
            nome=d["nome"],
            nivel=int(p.nivel),
            nivel_max=nivel_max,
            ativa=bool(p.ativa),
            divida=round(float(p.divida or 0), 2),
            energia=round(energia, 2),
            energia_max=cfg["energia_max"],
            energia_regen_por_segundo=cfg["energia_regen_por_segundo"],
            producao_dia=round(float(p.producao_dia or 0), 2),
            cap_diario=produtoras.cap_diario(p.nivel),
            lote_min=lo,
            lote_max=hi,
            custo_insumo_unidade=custo_unit,
            custo_insumo_lote=round(custo_unit * hi, 2),
            manutencao_dia=produtoras.manutencao_dia(float(d["custo_compra"]), p.nivel),
            custo_melhoria=custo_melhoria,
            cooldown_segundos=cfg["cooldown_segundos"],
            proxima_energia_em=prox_energia,
            proximo_clique_em=prox_clique,
            dia_vence_em=self._dia_vence_em(p, agora),
            ciclo_em=(_dt(p.ciclo_em) or agora).timestamp(),
        )
