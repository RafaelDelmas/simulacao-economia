"""Cartas de evento (manchetes) — cena narrativa por cima do choque.

Por que existe: um mercado que só muda de número não prende. A manchete dá
HISTÓRIA ao movimento ("greve nos portos" antes do carvão subir), transforma
a intervenção em cena e recompensa quem lê o noticiário: quem comprava
carvão sob embargo lucra, quem estava vendido apanha.

Mecânica:
- `cartas_evento.json` (ao lado deste arquivo) define as cartas e os
  períodos — editável SEM reiniciar: o arquivo é re-lido quando o mtime
  muda (checado a cada tick, no máximo a cada 5 s) e no início de cada
  disparo. JSON inválido mantém a última versão boa (warning no log).
- Uma carta sorteada (por `peso`, sem repetir as 3 últimas) dispara a cada
  intervalo sorteado entre `intervalo_min/máx_minutos`; o `impacto` da
  carta é multiplicado por um fator aleatório — nem toda "greve" balança
  o mercado igual.
- O efeito é o MESMO choque do admin (`shock_prices` sob lock do book,
  recortado na faixa nominal, book cruzado liquidado na hora, preço
  exibido e amostra do gráfico na hora).
- Publica `market.news` no event bus → WS → banner "📰 ÚLTIMA HORA" no
  frontend; admin pode disparar na hora (mestre de cena).

Quem lê:
- `BotActivity.cycle` (a cada ciclo de bots) via `tick()`;
- `NewsController` (GET /api/news + POST /news/disparar);
- frontend via WS (`market.news`).

Tudo em memória + arquivo: no reboot a agenda recomeça do zero (aceitável,
rodada de aula é reiniciada junto com o serviço).
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections import deque
from pathlib import Path

from sqlalchemy import update

from app.core.database import SessionLocal
from app.core.market.engine import faixa_preco, preco_vivo
from app.core.market.events import event_bus
from app.core.market.orderbook import order_book
from app.models.commodity import Commodity as CommodityModel
from app.models.order import Order as OrderModel
from app.models.price_tick import PriceTick

logger = logging.getLogger(__name__)

ARQUIVO = Path(__file__).with_name("cartas_evento.json")

_CONFIG_PADRAO = {
    "intervalo_min_minutos": 45.0,
    "intervalo_max_minutos": 75.0,
    "impacto_fator_min": 0.75,
    "impacto_fator_max": 1.25,
    "banner_segundos": 18,
    "historico_max": 20,
}


def _num(cfg: dict, chave: str, lo: float, hi: float, padrao: float) -> float:
    """Lê um número do config com clamp — JSON editado à mão não derruba o loop."""
    try:
        v = float(cfg.get(chave, padrao))
    except (TypeError, ValueError):
        return padrao
    return max(lo, min(hi, v))


class NewsManager:
    """Sorteia e aplica cartas de evento (singleton, mesmo espírito do regimes)."""

    def __init__(self):
        self._cfg = dict(_CONFIG_PADRAO)
        self._cartas: list[dict] = []
        self._mtime: float | None = None
        self._prox_leitura = 0.0  # checagem do arquivo (mtime) limitada a 5s
        self._prox = 0.0
        self._recentes: deque[str] = deque(maxlen=3)  # ids p/ não repetir
        self._ultimas: deque[dict] = deque(maxlen=int(_CONFIG_PADRAO["historico_max"]))
        self._carregar()
        self._reagendar()

    # ------------------------------------------------------------ leitura --

    @property
    def proxima_em(self) -> float:
        """Epoch da próxima manchete automática."""
        return self._prox

    def estado(self) -> dict:
        """Payload do GET /api/news (config + cartas + agenda + histórico)."""
        return {
            "config": dict(self._cfg),
            "cartas": list(self._cartas),
            "proxima_em": self._prox,
            "ultimas": list(self._ultimas),
        }

    # ------------------------------------------------------------ arquivo --

    def _carregar(self) -> None:
        """(Re)lê o JSON. Em erro mantém a última versão boa e loga warning."""
        try:
            mtime = ARQUIVO.stat().st_mtime
            dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("cartas de evento: %s não encontrado", ARQUIVO.name)
            return
        except (OSError, ValueError) as exc:  # ValueError cobre JSON inválido
            logger.warning(
                "cartas de evento: erro ao ler %s (%s) — mantendo a última versão",
                ARQUIVO.name,
                exc,
            )
            return

        bruto = dados.get("config", {}) if isinstance(dados, dict) else {}
        cartas_brutas = dados.get("cartas") if isinstance(dados, dict) else None
        if not isinstance(cartas_brutas, list) or not cartas_brutas:
            logger.warning(
                "cartas de evento: %s sem lista de cartas válida — mantendo a última versão",
                ARQUIVO.name,
            )
            return

        cfg = {
            "intervalo_min_minutos": _num(
                bruto, "intervalo_min_minutos", 0.05, 1440, 45.0
            ),
            "intervalo_max_minutos": _num(
                bruto, "intervalo_max_minutos", 0.05, 1440, 75.0
            ),
            "impacto_fator_min": _num(bruto, "impacto_fator_min", 0.1, 3.0, 0.75),
            "impacto_fator_max": _num(bruto, "impacto_fator_max", 0.1, 3.0, 1.25),
            "banner_segundos": int(_num(bruto, "banner_segundos", 3, 300, 18)),
            "historico_max": int(_num(bruto, "historico_max", 1, 100, 20)),
        }
        if cfg["intervalo_max_minutos"] < cfg["intervalo_min_minutos"]:
            cfg["intervalo_max_minutos"] = cfg["intervalo_min_minutos"]
        if cfg["impacto_fator_max"] < cfg["impacto_fator_min"]:
            cfg["impacto_fator_max"] = cfg["impacto_fator_min"]

        cartas: list[dict] = []
        for c in cartas_brutas:
            if not isinstance(c, dict):
                continue
            titulo = str(c.get("titulo") or "").strip()
            impacto = c.get("impacto")
            alvos = c.get("alvos")
            if (
                not titulo
                or not isinstance(impacto, (int, float))
                or not isinstance(alvos, list)
                or not alvos
            ):
                logger.warning("cartas de evento: carta inválida ignorada: %r", c)
                continue
            cartas.append(
                {
                    "id": str(c.get("id") or titulo.lower().replace(" ", "-")),
                    "emoji": str(c.get("emoji") or "📰"),
                    "titulo": titulo,
                    "alvos": [str(a) for a in alvos],
                    "impacto": float(impacto),
                    "peso": max(float(c.get("peso", 1) or 1), 0.01),
                }
            )
        if not cartas:
            logger.warning(
                "cartas de evento: nenhuma carta válida em %s — mantendo a última versão",
                ARQUIVO.name,
            )
            return

        self._cfg = cfg
        self._cartas = cartas
        self._ultimas = deque(self._ultimas, maxlen=cfg["historico_max"])
        self._mtime = mtime

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
        # Marca ANTES de ler: se o JSON estiver quebrado, o warning não
        # repete a cada 5 s — só tenta de novo quando o arquivo mudar.
        self._mtime = mtime
        self._carregar()
        # Mudou a agenda? Reagenda na hora — o professor editou para ver efeito.
        if self._prox > agora + 1:
            self._reagendar()

    # ----------------------------------------------------------- sortear --

    def _reagendar(self) -> None:
        self._prox = time.time() + random.uniform(
            self._cfg["intervalo_min_minutos"] * 60,
            self._cfg["intervalo_max_minutos"] * 60,
        )

    def _escolher(self, carta_id: str | None = None) -> dict | None:
        """Carta da vez: id específico (admin) ou sorteio por peso sem repetir as 3 últimas."""
        if not self._cartas:
            return None
        if carta_id:
            return next((c for c in self._cartas if c["id"] == carta_id), None)
        candidatas = [c for c in self._cartas if c["id"] not in self._recentes]
        if not candidatas:  #baralho inteiro esgotado: libera tudo
            candidatas = list(self._cartas)
        pesos = [c["peso"] for c in candidatas]
        return random.choices(candidatas, weights=pesos, k=1)[0]

    # ------------------------------------------------------------ disparo --

    def tick(self, commodities: list) -> None:
        """Roda a cada ciclo de bots: relógio + eventual re-leitura do JSON.

        A checagem do arquivo é limitada a 1x/5s (stat é barato, mas não a
        cada 100ms); o disparo em si só acontece quando o timer vence.
        """
        if not commodities:
            return
        self._checar_arquivo()
        if time.time() < self._prox:
            return
        self.disparar()

    def disparar(self, carta_id: str | None = None) -> dict | None:
        """Aplica uma carta (sorteada ou específica) e publica `market.news`.

        Devolve o payload publicado ou None (sem cartas / sem alvo válido).
        Nunca deixa exceção subir sem log — reagenda SEMPRE, senão o próximo
        ciclo de bots tentaria de novo em 100 ms.
        """
        try:
            payload = self._aplicar(carta_id)
        except Exception:
            logger.exception("cartas de evento: falha ao disparar carta %s", carta_id)
            payload = None
        finally:
            self._reagendar()
        return payload

    def _aplicar(self, carta_id: str | None) -> dict | None:
        self._checar_arquivo()
        carta = self._escolher(carta_id)
        if carta is None:
            logger.warning("cartas de evento: carta %r não existe", carta_id)
            return None

        sess = SessionLocal()
        try:
            linhas = sess.query(CommodityModel).all()
            alvos = self._resolver_alvos(carta, linhas)
            if not alvos:
                logger.warning(
                    "cartas de evento: %s sem alvo válido (%s) — nada aplicado",
                    carta["id"],
                    ", ".join(carta["alvos"]),
                )
                return None

            fator = random.uniform(
                self._cfg["impacto_fator_min"], self._cfg["impacto_fator_max"]
            )
            impacto = round(carta["impacto"] * fator, 2)

            logger.info(
                "cartas de evento: %s %r -> %s (%+.2f%%)",
                carta["id"],
                carta["titulo"],
                ", ".join(c.name for c in alvos),
                impacto,
            )

            movidas = 0
            preco_antes = preco_depois = None
            for c in alvos:
                antes = float(c.current_price or c.base_price or 0)
                alteradas = self._choque(sess, c, impacto)
                movidas += len(alteradas)
                if preco_antes is None:  # referência = primeiro alvo
                    preco_antes = antes
                    preco_depois = float(c.current_price or antes)
        finally:
            sess.close()

        payload = {
            "tipo": "manchete",
            "id": carta["id"],
            "titulo": carta["titulo"],
            "emoji": carta["emoji"],
            "commodity_id": alvos[0].id if len(alvos) == 1 else None,
            "alvos": [
                {"id": c.id, "name": c.name, "impacto": impacto} for c in alvos
            ],
            "impacto": impacto,
            "preco_antes": preco_antes,
            "preco_depois": preco_depois,
            "ordens_movidas": movidas,
            "segundos": self._cfg["banner_segundos"],
            "emitido_em": time.time(),
        }
        self._recentes.append(carta["id"])
        self._ultimas.appendleft(payload)
        event_bus.publish("market.news", payload)
        return payload

    def _resolver_alvos(self, carta: dict, linhas: list) -> list:
        """Converte os `alvos` da carta em commodities (pula congeladas)."""
        vivas = [c for c in linhas if not c.is_frozen]
        alvos = [str(a).strip() for a in carta["alvos"]]
        if "*" in alvos:
            return vivas
        if "aleatoria" in alvos:
            return [random.choice(vivas)] if vivas else []
        nomes = {a.lower() for a in alvos}
        return [c for c in vivas if c.name.lower() in nomes]

    def _choque(self, sess, c: CommodityModel, percent: float) -> list[tuple[int, float]]:
        """Aplica o choque numa alvo — mesmo caminho do `shock` do admin.

        Book primeiro (fonte da verdade, sob lock, faixa nominal), banco
        depois, preço exibido + PriceTick na hora (o gráfico pula no
        mesmo segundo). Retorna as ordens reprecificadas.
        """
        base = float(c.base_price or 0)
        floor, ceil = faixa_preco(base) if base > 0 else (0.01, None)
        alteradas = order_book.shock_prices(c.id, 1 + percent / 100, floor, ceil)
        for oid, preco in alteradas:
            sess.execute(update(OrderModel).where(OrderModel.id == oid).values(price=preco))
        novo = preco_vivo(
            order_book.best_bid_price(c.id), order_book.best_ask_price(c.id), base
        )
        if novo is not None:
            c.current_price = novo
            if base:
                c.variation_24h = round((novo - base) / base * 100, 2)
            sess.add(PriceTick(commodity_id=c.id, price=novo))
        sess.commit()
        return alteradas


# Instância compartilhada: bots, API e WS leem o MESMO estado.
manchetes = NewsManager()
