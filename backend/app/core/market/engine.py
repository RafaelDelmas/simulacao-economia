"""Market Engine skeleton.

Responsável pelo loop principal que:
1. Atualiza preços das commodities (variação por oferta/demanda).
2. Move bots (inserem ordens no order book).
3. Aplica taxa anti-inflação.
4. Dispara eventos via EventBus para o WebSocket broadcast.

Esta é uma estrutura esqueleta — a lógica completa de bots/taxas será implementada
nas próximas etapas (10 lotes de 120 bots, loop 100ms).
"""

import asyncio
import time
from typing import Dict, Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.market.events import event_bus
from app.core.market.orderbook import OrderBook
from app.models.commodity import Commodity
from app.models.price_tick import PriceTick
from sqlalchemy.orm import Session


def faixa_preco(base: float) -> tuple[float, float]:
    """Faixa permitida do preço em torno da base nominal da commodity."""
    amplitude = getattr(settings, "preco_amplitude_percentual", 30.0) / 100.0
    return base * (1 - amplitude), base * (1 + amplitude)


def limita_preco(preco: float, base: float) -> float:
    """Corta o preço na faixa nominal (impede bolha e colapso)."""
    if not base or base <= 0:
        return round(max(preco, 0.01), 2)
    limite_inferior, limite_superior = faixa_preco(base)
    return round(min(max(preco, limite_inferior), limite_superior), 2)


def preco_vivo(
    bid: float | None,
    ask: float | None,
    base: float,
    peso: float | None = None,
) -> float | None:
    """Preço exibido de uma commodity: meio da melhor compra/venda, com a
    puxada pro nominal e o corte na faixa. `None` quando não há book — o
    caller mantém o último preço conhecido.

    É a mesma conta do loop do engine; fica em função pra o admin conseguir
    recalcular o preço na hora de uma intervenção (choque, troca de base).
    """
    if bid and ask:
        preco = round((bid + ask) / 2, 2)
    elif bid or ask:
        preco = round(bid or ask, 2)
    else:
        return None
    if preco <= 0:
        return None
    if peso is None:
        peso = (
            max(
                0.0,
                min(getattr(settings, "preco_reversao_percentual", 20.0), 100.0),
            )
            / 100.0
        )
    # Primeiro a puxada pro nominal, depois o corte na faixa:
    # o preço sobe e desce com a oferta/demanda, mas não faz bolha.
    preco = preco * (1 - peso) + base * peso
    return limita_preco(preco, base)


def clamp_prices() -> int:
    """Devolve ao nominal os preços que estouraram a faixa. Retorna quantos ajustou.

    Chamado no boot: evita que o bot engine replique preço inflado de uma
    rodada anterior. Nesse caso o histórico de ticks também sai de cena —
    é dado derivado que se regenera em minutos e só poluiria o gráfico.
    """
    sess = SessionLocal()
    try:
        ajustados = 0
        for c in sess.query(Commodity).all():
            atual = float(c.current_price or 0)
            base = float(c.base_price or 0)
            if not base:
                continue
            inferior, superior = faixa_preco(base)
            if not (inferior <= atual <= superior):
                c.current_price = base
                c.variation_24h = 0.0
                ajustados += 1
        if ajustados:
            sess.query(PriceTick).delete()
        sess.commit()
        return ajustados
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


class MarketEngine:
    """Motor de simulação econômica (esqueleto)."""

    def __init__(self, order_book: OrderBook, db_session: Session | None = None):
        self.order_book = order_book
        self.db = db_session or SessionLocal()
        self.running = False
        self._last_sink = time.time()
        self._last_price_update = time.time()

    async def start(self):
        """Loop assíncrono principal — roda a cada bot_tick_ms ms."""
        self.running = True
        tick_ms = getattr(settings, "bot_tick_ms", 100)
        while self.running:
            try:
                await self._cycle()
            except Exception as exc:
                # Log e continua — não derruba o serviço
                import logging
                logging.getLogger(__name__).error(f"Error in market cycle: {exc}")
            await asyncio.sleep(tick_ms / 1000.0)

    async def stop(self):
        self.running = False
        await asyncio.sleep(0.1)

    async def _cycle(self):
        """Um ciclo do engine: price update + bot moves + tax."""
        now = time.time()
        dt = now - self._last_sink

        # 1. Atualiza preços e grava a amostra do gráfico a cada N segundos
        if now - self._last_price_update > getattr(settings, "preco_tick_segundos", 3):
            self._update_commodity_prices()
            self._last_price_update = now

        # 2. Bots inserem ordens no book — responsabilidade do BotEngine
        #    (app.core.market.bots), que roda no mesmo tick.

        # 3. Anti-inflação: taxa a cada intervalo de minutos (convertido para seconds)
        interval = getattr(settings, "taxa_sink_interval_minutos", 60)
        if dt >= interval * 60:
            await self._apply_sink_tax()
            self._last_sink = now

        # 4. Broadcast state via EventBus (WebSocket consumirá isso)
        try:
            snapshot = self.order_book.snapshot(0)  # placeholder; real commodity id virá do loop
            event_bus.publish("market.tick", {"timestamp": now, "snapshot": snapshot})
        except Exception:
            pass

    def _update_commodity_prices(self):
        """Preço corrente = meio da melhor compra/venda, mais amostra pro gráfico.

        É o book que manda: se faltar liquidez de um lado, o preço fica onde
        está (não inventa valor). Cada ciclo deixa uma amostra em `price_ticks` —
        é o que os gráficos do jogador leem.
        """
        import logging

        from app.models.commodity import Commodity as CommodityModel

        sess = SessionLocal()
        try:
            # Peso do nominal: a demanda move o preço, mas ele sempre volta
            # devagar pro valor de base (sem isso o book embola sozinho).
            peso = (
                max(
                    0.0,
                    min(getattr(settings, "preco_reversao_percentual", 20.0), 100.0),
                )
                / 100.0
            )
            for c in sess.query(CommodityModel).all():
                preco = preco_vivo(
                    self.order_book.best_bid_price(c.id),
                    self.order_book.best_ask_price(c.id),
                    float(c.base_price or 0),
                    peso,
                )
                if preco is None:
                    continue  # sem ordens: mantém o último preço conhecido
                c.current_price = preco
                base = float(c.base_price or 0)
                if base:
                    c.variation_24h = round((preco - base) / base * 100, 2)
                sess.add(PriceTick(commodity_id=c.id, price=preco))
            sess.commit()
        except Exception:
            sess.rollback()
            logging.getLogger(__name__).exception("falha ao atualizar os precos")
        finally:
            sess.close()

    async def _apply_sink_tax(self):
        """Taxa de carga perdida (item sink) — remove valor do mercado periodicamente.

        Esta é a implementação mínima: registra o evento e, no futuro, deduz do saldo
        dos usuários ou remove ordens do order book.
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Applying inflation sink tax (interval reached)")
        # Publia evento para futuras implementações (remover valor, ajustar saldos etc.)
        from app.core.market.events import event_bus
        event_bus.publish("tax.applied", {"rate_percent": settings.taxa_inflacao_percentual})
        # Placeholder: ajusta preços ligeiramente para cima (simulação de inflação controlada)
        from app.models.commodity import Commodity as CommodityModel
        sess = SessionLocal()
        try:
            for c in sess.query(CommodityModel).all():
                # Pequeno aumento de preço base para simular inflação
                c.base_price = round(c.base_price * (1 + settings.taxa_inflacao_percentual / 100), 2)
            sess.commit()
        except Exception:
            sess.rollback()
        finally:
            sess.close()