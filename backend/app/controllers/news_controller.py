from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.market.news import manchetes


class NewsController:
    """Camada de controle das cartas de evento (manchetes).

    O estado e o disparo moram no `NewsManager` (singleton em memória,
    compartilhado com o loop dos bots); o controller só traduz HTTP.
    """

    def __init__(self, db: Session):
        self.db = db

    def estado(self) -> dict:
        """GET /api/news — config vigente, cartas, agenda e últimas disparadas."""
        return manchetes.estado()

    def disparar(self, carta_id: str | None) -> dict:
        """POST /api/news/disparar — aplica a carta agora (admin).

        Sem id o sorteio é o mesmo do automático; com id inexistente, 404.
        """
        if carta_id:
            existe = any(c["id"] == carta_id for c in manchetes.estado()["cartas"])
            if not existe:
                raise NotFoundError(f"Carta de evento '{carta_id}' não encontrada")
        payload = manchetes.disparar(carta_id)
        if payload is None:
            raise ConflictError(
                "Nenhuma carta pôde ser disparada (mercado sem commodities "
                "válidas ou carta sem alvo) — veja o log do backend"
            )
        return {
            "detail": (
                f"{payload['emoji']} {payload['titulo']} — choque de "
                f"{payload['impacto']:+.1f}% em "
                f"{', '.join(a['name'] for a in payload['alvos'])}"
            ),
            "manchete": payload,
        }
