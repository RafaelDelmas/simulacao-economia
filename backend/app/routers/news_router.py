from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.news_controller import NewsController
from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.news import NewsDisparar

router = APIRouter(prefix="/news", tags=["news"])


def get_controller(db: Session = Depends(get_db)) -> NewsController:
    return NewsController(db)


@router.get("")
def get_news(controller: NewsController = Depends(get_controller)):
    """Cartas de evento: config vigente, baralho, próxima automática e últimas."""
    return controller.estado()


@router.post("/disparar")
def disparar(
    payload: NewsDisparar | None = None,
    _: User = Depends(get_current_admin),
    controller: NewsController = Depends(get_controller),
):
    """Dispara uma carta de evento agora (mestre de cena) — somente admin.

    Sem `id` no corpo sorteia como o automático; com `id` dispara aquela
    carta específica. O efeito é o mesmo choque do admin + manchete no WS.
    """
    return controller.disparar(payload.id if payload else None)
