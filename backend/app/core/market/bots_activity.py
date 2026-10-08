"""Activity per cycle for the BotEngine.

Cada ciclo o bot engine chama este módulo para gerar atividade no order book.
Estrutura: 10 lotes × 120 bots = 1200 bots totais.

Além do ruído básico, três camadas de psicologia moram aqui (o "roteiro" de
cada estado vive em `regimes.py`):
- **ordens agressivas** (`bots_frac_agressivas`): uma fração das ordens CRUZA
  o spread na hora — recompensa variável pra quem deixou ordem descansando
  no book; o resto continua esperando (a espera é parte do jogo);
- **baleia** (`bots_frac_baleia`): ordem rara com quantidade grande; quando o
  total que ela consumiu passa de `bots_baleia_qtd_min` vira `destaques` no
  snapshot de `bot.activity` (🐋 no feed do mercado). O anúncio lê o
  `executed_quantity` acumulado da PRÓPRIA ordem — o evento `order.executed`
  traz a quantidade do lado que zerou (o pedaço comido, quase sempre miúdo);
- **regime + FOMO**: viés de lado, deslocamento de preço e agressividade vêm
  do humor da commodity — os bots executam a tendência que o jogador lê no
  gráfico, e a janela FOMO bomba a compra por alguns segundos;
- **cartas de evento (manchetes)**: de tempos em tempos (`cartas_evento.json`)
  uma manchete "greve nos portos" dispara o choque no(s) alvo(s) e vira cena
  no feed — `manchetes.tick` roda aqui junto com os regimes.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from random import randint, uniform
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.market.engine import limita_preco
from app.core.market.news import manchetes
from app.core.market.regimes import regimes
from app.models.commodity import Commodity as CommodityModel  # type: ignore
from app.models.order import Order as OrderModel  # type: ignore

logger = logging.getLogger(__name__)


class BotActivity:
    """Gera ordens de bot a cada ciclo do engine."""

    def __init__(self):
        self.snapshot_data: dict | None = None
        # Ordens de baleia em acompanhamento: a fill só é anunciada quando o
        # `executed_quantity` DELA (total consumido) passa do limiar. Deque
        # drenado por `snapshot()` — popleft/append do CPython são atômicos
        # sob o GIL (bots no event loop, API em threadpool).
        self._baleias: deque[dict] = deque(maxlen=30)

    def _anunciar_baleias(self) -> list[dict]:
        """Drena as baleias que já consumiram `bots_baleia_qtd_min` un."""
        limite = getattr(settings, "bots_baleia_qtd_min", 20.0)
        agora = time.time()
        destaques: list[dict] = []
        ficam: deque[dict] = deque(maxlen=30)
        while self._baleias:
            item = self._baleias.popleft()
            ordem = item["ordem"]
            consumido = float(getattr(ordem, "executed_quantity", 0) or 0)
            if consumido >= limite:
                destaques.append(
                    {
                        "commodity_id": ordem.commodity_id,
                        "side": ordem.side,
                        "price": float(ordem.price),
                        "quantity": round(consumido, 2),
                    }
                )
            elif not ordem.filled and agora - item["desde"] < 600:
                ficam.append(item)  # ainda comendo (ou expirou do book: descarta)
        self._baleias = ficam
        return destaques

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

            # Regimes/FOMO e cartas de evento rotacionam por aqui: a lista de
            # ids já está na mão (sem query extra) e commodity congelada fica
            # de fora de propósito.
            regimes.tick([c.id for c in commodities])
            manchetes.tick(commodities)

            frac_agressivas = getattr(settings, "bots_frac_agressivas", 0.12)

            # Insere 1 ordem por lote este ciclo (10 ordens totais por ciclo)
            for _ in range(getattr(settings, "bots_lotes", 10)):
                c = commodities[randint(0, len(commodities) - 1)]
                cfg = regimes.config(c.id)
                fomo = regimes.fomo_ativo(c.id)

                # Lado: viés do regime (FOMO = pressão de compra quase unânime)
                vies_bid = 0.85 if fomo else cfg["vies_bid"]
                side = "bid" if uniform(0, 1) < vies_bid else "ask"

                # `atual` ancora a citação (o preço vivo da rodada);
                # `nominal` é a âncora da faixa — clampear contra o preço
                # atual faria a faixa vagar junto e não clampear nada.
                atual = float(c.current_price or c.base_price or 1)
                nominal = float(c.base_price or c.current_price or 1)

                # Sorteios de forma (baleia é rara e sempre agressiva)
                eh_baleia = uniform(0, 1) < getattr(settings, "bots_frac_baleia", 0.001)
                mult = cfg["mult_agress"] * (3.0 if fomo else 1.0)
                eh_agressiva = eh_baleia or uniform(0, 1) < min(
                    frac_agressivas * mult, 0.9
                )

                if eh_agressiva:
                    # Cruza o spread: executa na hora contra quem descansa.
                    # Sem lado oposto, "abre o lado" pertinho do nominal.
                    oposto = (
                        order_book.best_ask_price(c.id)
                        if side == "bid"
                        else order_book.best_bid_price(c.id)
                    )
                    if oposto:
                        price = float(oposto)
                    elif side == "bid":
                        price = atual * (1 + uniform(0.001, 0.02))
                    else:
                        price = atual * (1 - uniform(0.001, 0.02))
                else:
                    # Passivo deslocado na direção do regime (isso é a
                    # tendência que o gráfico mostra depois)
                    price = atual * (1 + uniform(cfg["off_min"], cfg["off_max"]))

                if eh_baleia:
                    qty = uniform(
                        settings.bots_baleia_qtd_min, settings.bots_baleia_qtd_max
                    )
                else:
                    qty = uniform(0.1, 5.0) * (2.0 if fomo else 1.0)

                price = limita_preco(price, nominal)

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
                if eh_baleia:
                    # Acompanha a baleia: o anúncio (🐋) sai quando o total
                    # consumido por ESTA ordem passar do limiar
                    self._baleias.append({"ordem": order, "desde": time.time()})
                # Persiste no banco
                sess.add(order)
            sess.commit()
        except Exception:
            sess.rollback()
            # Log alto (regra dos engines): swallow silencioso já escondeu
            # a parada dos bots aqui dentro.
            logger.exception("falha no ciclo dos bots")
        finally:
            sess.close()

    def snapshot(self) -> dict | None:
        """Retorna dados para broadcast via WebSocket.

        `destaques` é drenado aqui: cada 🐋 aparece uma única vez no feed.
        """
        return {
            "bots_active": getattr(settings, "bots_total", 1200),
            "lotes": getattr(settings, "bots_lotes", 10),
            "destaques": self._anunciar_baleias(),
        }
