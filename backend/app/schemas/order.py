from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderBase(BaseModel):
    commodity_id: int = Field(..., ge=1)
    side: str = Field(..., pattern="^(bid|ask)$")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., ge=0)


class OrderCreate(OrderBase):
    pass


class OrderOut(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    # quantity = 0 quando a ordem foi totalmente preenchida.
    # (A entrada continua exigindo gt=0 — ver OrderCreate.)
    quantity: float = Field(..., ge=0)
    # Quanto desta ordem já executou (soma dos matches); o ticker lê esta coluna.
    executed_quantity: float = Field(0.0, ge=0)

    id: int
    user_id: int | None
    filled: bool
    created_at: datetime


class MyOrdersOut(BaseModel):
    """Ordens do jogador logado: o que está no book e o que já executou."""

    open: list[OrderOut]
    filled: list[OrderOut]