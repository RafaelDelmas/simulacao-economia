"""Dependências de autenticação/autorização (usuário logado e perfil admin)."""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve o usuário logado a partir do token Bearer enviado na request."""
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception:
        raise UnauthorizedError("Token inválido ou expirado")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Usuário inválido ou inativo")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Bloqueia o acesso a usuários sem perfil de administrador."""
    if not user.is_admin:
        raise ForbiddenError("Acesso restrito ao administrador")
    return user
