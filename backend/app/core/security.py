"""Hash de senhas e emissão/validação de tokens JWT."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Gera o hash bcrypt de uma senha."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Confere uma senha contra o hash armazenado."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    """Emite um token JWT assinado para o usuário autenticado."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Valida a assinatura/expiração e decodifica o payload do token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
