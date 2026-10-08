"""Produtoras (clicker de estoque) — segunda forma de conseguir estoque.

Por que existe: comprar no book é a via "de mercado"; a produtora é a via
"de produção" — o jogador compra o meio de produção, trabalha nele
(cliques) e paga pra mantê-lo vivo. Ensina custo de oportunidade, capital
de giro e a diferença entre estoque comprado e estoque produzido.

Mecânica (todos os números em `produtoras.json`, na RAIZ do backend):
- uma produtora por commodity por jogador (`UNIQUE user_id + commodity_id`);
- cada clique produz um lote (~`lote_base` unidades no nível 1, ±`lote_variacao`,
  com `jackpot_chance` de "boa safra" ×`jackpot_fator`) e COBRA insumo:
  `unidades × base_price × insumo_fracao` — margem bruta ~20% no nominal.
  Saturar o mercado derruba o preço até o piso da faixa e produzir vira
  prejuízo: o clicker não encanta a oferta/demanda, ele a EXPÕE;
- trava de tempo: `cooldown_segundos` entre cliques (anti-macro, servidor)
  + energia (rajada de `energia_max / energia_por_clique` cliques, depois
  o ritmo é `energia_regen_por_segundo`);
- trava de volume: `cap_diario` por dia de jogo (`dia_segundos`); o teto
  chega antes da paciência do zé-zerinho;
- trava de caixa: manutenção diária cobrada por varredura (e também na
  interação, sob o MESMO lock — só uma das duas cobra). Sem saldo →
  produtora inadimplente (`ativa=False`), trava até quitar a `divida`
  (que não compõe: no máximo 1 dia). Saldo nunca fica negativo.

Leitura quente do JSON: mtime checado no máximo 1x/5s; JSON inválido
mantém a última versão boa e loga warning (mesmo contrato do
`cartas_evento.json`).

Quem lê:
- `ProdutorasController` (GET/POST /api/produtoras...);
- `prune_loop` via `produtores_tick()` (varredura de manutenção).

Locking: produtora e user são travados sempre na ORDEM user → producer
(`with_for_update`) — mesma ordem do DELETE de usuário (user primeiro),
senão dois deletes concorrentes poderiam deadlatch com um clique.
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.commodity import Commodity
from app.models.produtora import Producer
from app.models.user import User

logger = logging.getLogger(__name__)

# Raiz do backend (app/core/market/produtoras.py -> 3 níveis acima).
ARQUIVO = Path(__file__).resolve().parents[3] / "produtoras.json"

_CONFIG_PADRAO = {
    "dia_segundos": 1200.0,        # 1 dia de jogo = 20 min
    "varredura_segundos": 60.0,    # frequência da cobrança de manutenção
    "energia_max": 100.0,
    "energia_por_clique": 20.0,    # rajada de 5 cliques
    "energia_regen_por_segundo": 4.0,  # steady-state ~12 cliques/min
    "cooldown_segundos": 1.0,
    "lote_base": 3.0,
    "lote_nivel_fator": 1.5,
    "lote_variacao": 0.25,
    "cap_diario_base": 25.0,
    "cap_nivel_fator": 1.5,
    "insumo_fracao": 0.8,          # custo do clique vs preço NOMINAL
    "custo_fracao_base": 8.0,      # default de compra vs preço nominal
    "custo_melhoria_fracao": 1.5,  # melhoria n->n+1 = compra × 1.5 × 2^n
    "custo_melhoria_fator": 2.0,
    "nivel_max": 5,
    "manutencao_fracao": 0.05,     # manutenção diária vs custo de compra
    "manutencao_nivel_fator": 1.8,
    "manutencao_dias_cobranca_max": 2.0,
    "jackpot_chance": 0.05,
    "jackpot_fator": 3.0,
}

# Limites por chave — JSON editado à mão nunca derruba o jogo.
_LIMITES = {
    "dia_segundos": (30.0, 86400.0),
    "varredura_segundos": (5.0, 3600.0),
    "energia_max": (10.0, 10000.0),
    "energia_por_clique": (1.0, 10000.0),
    "energia_regen_por_segundo": (0.1, 1000.0),
    "cooldown_segundos": (0.0, 60.0),
    "lote_base": (0.5, 10000.0),
    "lote_nivel_fator": (1.0, 10.0),
    "lote_variacao": (0.0, 0.9),
    "cap_diario_base": (1.0, 1_000_000.0),
    "cap_nivel_fator": (1.0, 10.0),
    "insumo_fracao": (0.0, 10.0),
    "custo_fracao_base": (0.1, 1000.0),
    "custo_melhoria_fracao": (0.0, 100.0),
    "custo_melhoria_fator": (1.0, 10.0),
    "nivel_max": (1.0, 50.0),
    "manutencao_fracao": (0.0, 1.0),
    "manutencao_nivel_fator": (1.0, 10.0),
    "manutencao_dias_cobranca_max": (1.0, 30.0),
    "jackpot_chance": (0.0, 1.0),
    "jackpot_fator": (1.0, 100.0),
}


def _num(cfg: dict, chave: str, padrao: float) -> float:
    """Lê um número do config com clamp nos limites da chave."""
    lo, hi = _LIMITES[chave]
    try:
        v = float(cfg.get(chave, padrao))
    except (TypeError, ValueError):
        return padrao
    return max(lo, min(hi, v))


def _dt(d: datetime | None) -> datetime | None:
    """Aware em UTC: SQLite devolve naive, Postgres devolve aware."""
    if d is None:
        return None
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)


class ProdutorasManager:
    """Config quente + fórmulas de produção (singleton, espírito do regimes)."""

    def __init__(self):
        self._cfg = dict(_CONFIG_PADRAO)
        self._produtores_cfg: dict[str, dict] = {}
        self._mtime: float | None = None
        self._prox_leitura = 0.0  # checagem do mtime limitada a 5s
        self._prox_varredura = 0.0
        self._carregar()

    # ------------------------------------------------------------ leitura --

    @property
    def cfg(self) -> dict:
        return self._cfg

    def _carregar(self) -> None:
        """(Re)lê o JSON. Em erro mantém a última versão boa e loga warning."""
        try:
            mtime = ARQUIVO.stat().st_mtime
            dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("produtoras: %s não encontrado", ARQUIVO.name)
            return
        except (OSError, ValueError) as exc:  # ValueError cobre JSON inválido
            logger.warning(
                "produtoras: erro ao ler %s (%s) — mantendo a última versão",
                ARQUIVO.name,
                exc,
            )
            return

        if not isinstance(dados, dict):
            logger.warning(
                "produtoras: %s não é um objeto — mantendo a última versão",
                ARQUIVO.name,
            )
            return

        bruto = dados.get("config", {})
        if not isinstance(bruto, dict):
            bruto = {}
        cfg = {chave: _num(bruto, chave, pad) for chave, pad in _CONFIG_PADRAO.items()}

        produtores: dict[str, dict] = {}
        pb = dados.get("produtores", {})
        if isinstance(pb, dict):
            for nome, entrada in pb.items():
                if not isinstance(entrada, dict):
                    continue
                try:
                    custo = max(1.0, min(1e7, float(entrada.get("custo_compra", 0))))
                except (TypeError, ValueError):
                    continue
                if custo <= 0:
                    continue
                produtores[str(nome).strip()] = {
                    "emoji": str(entrada.get("emoji") or "🏭"),
                    "nome": str(entrada.get("nome") or f"Produtora de {nome}"),
                    "custo_compra": round(custo, 2),
                }

        self._cfg = cfg
        self._produtores_cfg = produtores
        self._mtime = mtime
        logger.info(
            "produtoras: config recarregado (dia %.0fs, %d produtores no catálogo)",
            cfg["dia_segundos"],
            len(produtores),
        )

    def _checar_arquivo(self) -> None:
        """Re-lê o JSON se o mtime mudou (no máximo a cada 5 s)."""
        agora = time.time()
        if agora < self._prox_leitura:
            return
        self._prox_leitura = agora + 5.0
        try:
            mtime = ARQUIVO.stat().st_mtime
        except OSError:
            return
        if self._mtime is not None and mtime == self._mtime:
            return
        self._mtime = mtime  # antes de ler: warning não repete a cada 5 s
        self._carregar()

    # ------------------------------------------------------------ fórmulas --

    def def_da_commodity(self, com: Commodity) -> dict:
        """Entrada do catálogo para uma commodity (default p/ commodity nova)."""
        entrada = self._produtores_cfg.get(com.name)
        base = float(com.base_price or 0)
        if entrada is None:
            return {
                "emoji": "🏭",
                "nome": f"Produtora de {com.name}",
                "custo_compra": round(base * self._cfg["custo_fracao_base"], 2),
            }
        return dict(entrada)

    def lote(self, nivel: int) -> tuple[int, int]:
        """Faixa (min, max) de unidades por clique no nível dado."""
        centro = self._cfg["lote_base"] * (self._cfg["lote_nivel_fator"] ** (nivel - 1))
        var = self._cfg["lote_variacao"]
        return max(1, round(centro * (1 - var))), max(1, round(centro * (1 + var)))

    def cap_diario(self, nivel: int) -> float:
        return round(
            self._cfg["cap_diario_base"]
            * (self._cfg["cap_nivel_fator"] ** (nivel - 1)),
            2,
        )

    def custo_melhoria(self, custo_compra: float, nivel: int) -> float:
        """Melhoria n -> n+1: cresce ×fator por nível (progressão cara)."""
        return round(
            custo_compra
            * self._cfg["custo_melhoria_fracao"]
            * (self._cfg["custo_melhoria_fator"] ** (nivel - 1)),
            2,
        )

    def manutencao_dia(self, custo_compra: float, nivel: int) -> float:
        return round(
            custo_compra
            * self._cfg["manutencao_fracao"]
            * (self._cfg["manutencao_nivel_fator"] ** (nivel - 1)),
            2,
        )

    def custo_insumo(self, unidades: float, base_price: float) -> float:
        """Custo do lote: ~0,8 × preço NOMINAL por unidade — a trava real."""
        return round(unidades * base_price * self._cfg["insumo_fracao"], 2)

    def rolar_lote(self, nivel: int) -> tuple[int, bool]:
        """Sorteia o lote de um clique: variação + chance de boa safra."""
        lo, hi = self.lote(nivel)
        unidades = random.randint(lo, hi)
        jackpot = random.random() < self._cfg["jackpot_chance"]
        if jackpot:
            unidades = max(1, round(unidades * self._cfg["jackpot_fator"]))
        return unidades, jackpot

    # -------------------------------------------------------- manutenção --

    def produtores_tick(self) -> dict:
        """Chamado pelo `prune_loop`: varredura de manutenção, auto-throttled."""
        self._checar_arquivo()
        agora = time.time()
        if agora < self._prox_varredura:
            return {"pulado": True}
        self._prox_varredura = agora + self._cfg["varredura_segundos"]
        try:
            return self.varrer_manutencao()
        except Exception:
            logger.exception("produtoras: varredura de manutenção falhou")
            return {"erro": True}

    def varrer_manutencao(self) -> dict:
        """Cobra manutenção das produtoras com o dia vencido.

        Regras sob o lock user → producer:
        - ativa + saldo: debita manutenção × min(dias, cap) e zera o cap;
        - ativa + SEM saldo: vira inadimplente com dívida de 1 dia (não
          compõe — quem sumiu não é esfolado ao voltar);
        - inadimplente + saldo: quita e reativa.
        """
        corte = datetime.now(timezone.utc) - timedelta(
            seconds=self._cfg["dia_segundos"]
        )
        sess = SessionLocal()
        cobradas = paradas = quitadas = 0
        try:
            # Vencidas + inadimplentes: as segundas são revisitadas aqui pra
            # quitar a dívida ASSIM que o saldo cobrir (sem esperar o dia virar).
            vencidas = (
                sess.query(Producer)
                .filter(or_(Producer.ciclo_em <= corte, Producer.ativa.is_(False)))
                .all()
            )
            for p in vencidas:
                user, prod = self._travar(sess, p.user_id, p.id)
                if user is None or prod is None:
                    continue  # apagado nesse meio-tempo
                if prod.ativa and _dt(prod.ciclo_em) > corte:
                    continue  # outra transação já rolou o dia
                try:
                    r = self._rolar_dia(sess, user, prod)
                    cobradas += r.get("cobrada", 0)
                    paradas += r.get("parada", 0)
                    quitadas += r.get("quitada", 0)
                    sess.commit()
                except Exception:
                    sess.rollback()
                    logger.exception(
                        "produtoras: manutenção falhou em producer=%s user=%s",
                        prod.id,
                        prod.user_id,
                    )
        finally:
            sess.close()
        if cobradas or paradas or quitadas:
            logger.info(
                "produtoras: manutenção — %s cobradas, %s paradas (sem saldo), "
                "%s quitadas",
                cobradas,
                paradas,
                quitadas,
            )
        return {"cobradas": cobradas, "paradas": paradas, "quitadas": quitadas}

    @staticmethod
    def _travar(
        sess: Session, user_id: int, producer_id: int
    ) -> tuple[User | None, Producer | None]:
        """Trava user e producer SEMPRE nessa ordem (evita deadlock)."""
        user = (
            sess.query(User).filter(User.id == user_id).with_for_update().first()
        )
        prod = (
            sess.query(Producer)
            .filter(Producer.id == producer_id)
            .with_for_update()
            .first()
        )
        return user, prod

    def _rolar_dia(self, sess: Session, user: User, prod: Producer) -> dict:
        """Cobra a manutenção vencida, quita dívida e zera o cap. Sob lock.

        Usado pela varredura E pela interação (clicar também rola o dia) —
        a checagem `ciclo_em <= corte` sob lock garante que só uma delas
        cobra. Inadimplente é tratado MESMO fora do virar do dia: quita
        assim que o saldo cobrir (a varredura re-entra por `ativa = false`).
        Devolve contadores pro log da varredura.
        """
        agora = datetime.now(timezone.utc)
        corte = agora - timedelta(seconds=self._cfg["dia_segundos"])
        resultado: dict = {"cobrada": 0, "parada": 0, "quitada": 0}

        if not prod.ativa:
            # Inadimplente: só quita (não cobra de novo, dívida não compõe).
            if prod.divida > 0 and float(user.balance or 0) >= prod.divida - 1e-9:
                user.balance = round(float(user.balance or 0) - prod.divida, 2)
                prod.divida = 0.0
                prod.ativa = True
                resultado["quitada"] = 1
                logger.info(
                    "produtoras: dívida quitada e produtora reativada "
                    "(user=%s producer=%s)", user.id, prod.id,
                )
            if _dt(prod.ciclo_em) > corte:
                return resultado  # quitou sem virar o dia: cap continua
            # Virou o dia junto: segue e zera o cap no fim.

        if _dt(prod.ciclo_em) > corte:
            return resultado

        dias_decorridos = max(
            1, int((agora - _dt(prod.ciclo_em)).total_seconds() // self._cfg["dia_segundos"])
        )
        custo_compra = self._custo_compra_de(sess, prod.commodity_id)
        diaria = self.manutencao_dia(custo_compra, prod.nivel)

        if prod.ativa:
            custo = round(
                diaria * min(dias_decorridos, self._cfg["manutencao_dias_cobranca_max"]),
                2,
            )
            if float(user.balance or 0) >= custo - 1e-9:
                user.balance = round(float(user.balance or 0) - custo, 2)
                resultado["cobrada"] = 1
            else:
                # Sem saldo: para com dívida de 1 dia (não composta).
                prod.ativa = False
                prod.divida = diaria
                resultado["parada"] = 1
                logger.warning(
                    "produtoras: produtora parada (sem saldo p/ manutenção) "
                    "user=%s producer=%s divida=%s", user.id, prod.id, diaria,
                )

        prod.ciclo_em = agora
        prod.producao_dia = 0.0
        return resultado

    def _custo_compra_de(self, sess: Session, commodity_id: int) -> float:
        """Custo de compra (default) de uma commodity — base dos custos."""
        com = sess.get(Commodity, commodity_id)
        if com is None:
            return 0.0
        entrada = self.def_da_commodity(com)
        return float(entrada["custo_compra"])


# Instância compartilhada: API e prune loop leem o MESMO estado.
produtoras = ProdutorasManager()
