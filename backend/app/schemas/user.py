from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    is_active: bool
    balance: float  # saldo em dinheiro do jogador
    streak: int = 0  # combo de vendas lucrativas (🔥 no frontend)
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=4, max_length=128)
    is_admin: bool = False
    # Saldo inicial. Se omitido, entra `jogo_inicial_saldo` do .env.
    balance: float | None = Field(default=None, ge=0)


class UserUpdate(BaseModel):
    """Intervenção do admin no saldo: absoluto OU variação (ex.: bônus/multa)."""

    balance: float | None = None  # define o saldo final
    delta: float | None = None     # soma/subtrai do saldo atual
