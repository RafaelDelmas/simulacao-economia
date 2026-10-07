from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.position_controller import PositionController
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.position import PositionOut

router = APIRouter(prefix="/positions", tags=["positions"])


def get_controller(db: Session = Depends(get_db)) -> PositionController:
    return PositionController(db)


@router.get("", response_model=list[PositionOut])
def my_positions(
    user: User = Depends(get_current_user),
    controller: PositionController = Depends(get_controller),
):
    """Estoque do jogador logado: quanto tem de cada commodity."""
    return controller.list_mine(user.id)
