"""Regimes de humor por commodity + janelas FOMO (psicologia do mercado).

Por que existe: um book alimentado só por ruído aleatório não se lê — o
jogador não tem o que estudar nem o que "acertar". O regime dá tendência
visível (a figura no gráfico vira legível) e cria o contraste psicológico
bom: na euforia o spread dos passivos abre, quem compra com pressa paga caro
e quem deixou uma ordem boa descansando é premiado quando as ordens
agressivas dos bots cruzam nelas.

Mecânica:
- Cada commodity tem um estado em `REGIMES` e uma próxima troca (2–5 min,
  `regime_minutos_*`). A transição publica `market.regime` no event bus.
- De tempos em tempos (`fomo_intervalo_*`) uma commodity aleatória ganha uma
  janela de `fomo_duracao_*` segundos com pressão de compra forte — quem está
  online pega a onda, quem saiu perde. Publica `market.event`.

Tudo em memória: no reboot o mercado começa "calmo" de novo — aceitável,
rodada de aula é reiniciada junto com o serviço. Quem lê:
- `BotActivity.cycle` (a cada tick dos bots) via `config()`/`fomo_ativo()`;
- `MarketEngine` (payload do `market.tick`) via `fomo_payload()`;
- `CommodityController` (chip no card) via `de()`.
"""

from __future__ import annotations

import random
import time

from app.core.config import settings
from app.core.market.events import event_bus

# vies_bid   -> fração de ordens de bot no lado compra (0.5 = sem viés)
# mult_agress-> multiplicador da fração de ordens que cruzam o spread
# off_min/max-> deslocamento do preço passivo em relação ao preço atual
REGIMES: dict[str, dict] = {
    "calmo": {"vies_bid": 0.50, "mult_agress": 1.0, "off_min": -0.10, "off_max": 0.10},
    "alta": {"vies_bid": 0.70, "mult_agress": 1.0, "off_min": -0.02, "off_max": 0.10},
    # euforia: passivos longe do meio (spread largo) + agressão em dobro
    "euforia": {"vies_bid": 0.80, "mult_agress": 2.0, "off_min": 0.00, "off_max": 0.12},
    "correcao": {"vies_bid": 0.25, "mult_agress": 1.0, "off_min": -0.12, "off_max": 0.02},
}

# Vizinhos possíveis de cada estado (repetição = peso maior na escolha).
# O ciclo alto → euforia → correção → calmo é o que dá "história" ao gráfico.
_PROXIMOS: dict[str, list[str]] = {
    "calmo": ["alta", "alta", "correcao", "calmo"],
    "alta": ["euforia", "euforia", "calmo", "alta"],
    "euforia": ["correcao", "correcao", "calmo", "euforia"],
    "correcao": ["calmo", "calmo", "alta", "correcao"],
}


class RegimeManager:
    """Estado de humor por commodity + a janela FOMO ativa (singleton)."""

    def __init__(self):
        self._estado: dict[int, str] = {}
        self._prox_troca: dict[int, float] = {}
        self._fomo: dict | None = None  # {commodity_id, titulo, fim}
        self._prox_fomo: float = time.time() + settings.fomo_intervalo_minutos * 60

    # ------------------------------------------------------------ leitura --

    def de(self, commodity_id: int) -> str:
        """Estado atual da commodity ("calmo" antes da primeira troca)."""
        return self._estado.get(commodity_id, "calmo")

    def config(self, commodity_id: int) -> dict:
        """Parâmetros de bot para o regime atual (nunca é None)."""
        return REGIMES[self.de(commodity_id)]

    def fomo_ativo(self, commodity_id: int) -> bool:
        return bool(
            self._fomo
            and self._fomo["commodity_id"] == commodity_id
            and time.time() < self._fomo["fim"]
        )

    def fomo_payload(self) -> dict | None:
        """Janela ativa pro payload do `market.tick` (segundos restantes)."""
        if not self._fomo or time.time() >= self._fomo["fim"]:
            return None
        return {
            "commodity_id": self._fomo["commodity_id"],
            "titulo": self._fomo["titulo"],
            "segundos_restantes": round(self._fomo["fim"] - time.time()),
        }

    # ------------------------------------------------------------ escrita --

    def tick(self, commodity_ids: list[int]) -> None:
        """Roda a cada ciclo de bots: rotaciona regimes e a janela FOMO."""
        if not commodity_ids:
            return
        agora = time.time()

        for cid in commodity_ids:
            if agora < self._prox_troca.get(cid, 0):
                continue
            atual = self.de(cid)
            novo = random.choice(_PROXIMOS[atual])
            duracao = random.uniform(
                settings.regime_minutos_min, settings.regime_minutos_max
            ) * 60
            self._estado[cid] = novo
            self._prox_troca[cid] = agora + duracao
            if novo != atual:
                event_bus.publish(
                    "market.regime",
                    {
                        "commodity_id": cid,
                        "regime": novo,
                        "segundos": round(duracao),
                    },
                )

        # Janela FOMO: expira a anterior e abre a próxima no intervalo certo
        if self._fomo and agora >= self._fomo["fim"]:
            self._fomo = None
        if self._fomo is None and agora >= self._prox_fomo:
            cid = random.choice(commodity_ids)
            dur = settings.fomo_duracao_segundos
            self._fomo = {
                "commodity_id": cid,
                "titulo": "Janela de oportunidade",
                "fim": agora + dur,
            }
            self._prox_fomo = agora + settings.fomo_intervalo_minutos * 60
            event_bus.publish(
                "market.event",
                {
                    "commodity_id": cid,
                    "titulo": "Janela de oportunidade",
                    "tipo": "fomo",
                    "segundos": dur,
                },
            )


# Instância compartilhada: engine, bots, API e WS leem o MESMO estado.
regimes = RegimeManager()
