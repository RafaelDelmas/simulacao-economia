"""Bot Engine skeleton.

Estrutura: 10 lotes × 120 bots em memória RAM.
Loop assíncrono a cada 100ms (0.1s).
Esta é uma estrutura esqueleta — a lógica de decisão de preço/quantidade
será implementada nas próximas etapas.

O módulo expõe:
- `BotEngine.start()` → loop assíncrono.
- `BotEngine.stop()` → encerra o loop.
- Eventos via `event_bus` para que o WebSocket reflita a atividade.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any

from app.core.config import settings
from app.core.market.events import event_bus
from app.core.market.bots_activity import BotActivity
from app.core.market.taxes import AntiInflation


logger = logging.getLogger(__name__)


class BotEngine:
    """Motor de bots: 10 lotes de 120 bots cada, loop 100ms."""

    def __init__(self, order_book: Any, anti_inflation: Any | None = None):
        self.order_book = order_book
        self.anti_inflation = anti_inflation or AntiInflation()
        self.running = False
        self._task: asyncio.Task | None = None
        self._activity = BotActivity()

    async def start(self):
        """Inicia o loop assíncrono dos bots."""
        self.running = True
        tick = getattr(settings, "bot_tick_ms", 100) / 1000.0  # para seconds
        self._task = asyncio.create_task(self._loop(tick))

    async def stop(self):
        """Para o loop dos bots."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self, tick: float):
        """Loop principal: a cada tick, os bots inserem/ajustam ordens."""
        logger.info("Bot engine loop started, tick=%.1fms", tick * 1000)
        try:
            while self.running:
                try:
                    await self._cycle()
                except Exception as exc:
                    logger.error("Error in bot cycle: %s", exc)
                await asyncio.sleep(tick)
        finally:
            logger.info("Bot engine loop stopped")

    async def _cycle(self):
        """Um ciclo: atividade dos bots + possível taxação."""
        # Insere ordens sintéticas via BotActivity
        await self._activity.cycle(self.order_book)
        # Publica activity snapshot para o WS
        try:
            ev = self._activity.snapshot()
            if ev:
                event_bus.publish("bot.activity", ev)
        except Exception:
            pass