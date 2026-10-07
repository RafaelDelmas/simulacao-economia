from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.user_controller import UserController
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def get_controller(db: Session = Depends(get_db)) -> UserController:
    return UserController(db)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, controller: UserController = Depends(get_controller)):
    """Autentica usuário e devolve o token Bearer."""
    user = controller.authenticate(payload.username, payload.password)
    token = create_access_token(
        user_id=user.id, username=user.username, is_admin=user.is_admin
    )
    return TokenOut(access_token=token, user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """Retorna o usuário autenticado (valida o token enviado)."""
    return user
