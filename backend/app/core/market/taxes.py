"""Anti‑Inflação: imposto dinâmico automático e taxa de carga perdida (item sink).

Esta estrutura será conectada ao MarketEngine.loop.
- Taxa percentual: lida via `settings.taxa_inflacao_percentual`.
- Sink interval: `settings.taxa_sink_interval_minutos` (quantos minutos entre cada aplicação).
- O `event_bus.publish("tax.applied", ...)` pode ser ouvido por serviços externos
  (ex.: remover valor de wallets, ajustar ordens, etc.).
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.market.events import event_bus


class AntiInflation:
    """Wrapper simples que expõe o estado da inflação para o engine e WS."""

    @property
    def current_rate(self) -> float:
        return float(settings.taxa_inflacao_percentual)

    @property
    def sink_interval_seconds(self) -> int:
        return int(settings.taxa_sink_interval_minutos * 60)

    def tick(self):
        """Chamado a cada loop do engine. Publica evento se o intervalo se esgotou."""
        # O próprio engine cuida do intervalo; este método expõe a taxa atual.
        return self.current_rate