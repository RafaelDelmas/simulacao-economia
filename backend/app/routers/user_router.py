from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.user_controller import UserController
from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def get_controller(db: Session = Depends(get_db)) -> UserController:
    return UserController(db)


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(get_current_admin),
    controller: UserController = Depends(get_controller),
):
    """Lista todos os usuários — somente admin."""
    return controller.list()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _: User = Depends(get_current_admin),
    controller: UserController = Depends(get_controller),
):
    """Cria um novo usuário — somente admin."""
    return controller.create(payload)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(get_current_admin),
    controller: UserController = Depends(get_controller),
):
    """Ajusta o saldo do jogador (define final ou soma/desconta) — admin."""
    return controller.update_balance(user_id, payload)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    controller: UserController = Depends(get_controller),
):
    """Apaga o jogador: cancela ordens abertas, some com estoque e saldo.

    As trocas já executadas ficam no histórico. Não dá pra apagar a própria
    conta nem o último admin.
    """
    return controller.delete(user_id, actor=admin)
