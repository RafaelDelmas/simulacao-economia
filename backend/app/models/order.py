from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Order(Base):
    """Ordem de compra/venda no order book de commodities."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    commodity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commodities.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    side: Mapped[str] = mapped_column(
        String(4), nullable=False
    )  # "bid" (compra) ou "ask" (venda)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    # Soma do que já executou. `quantity` é o RESTANTE no book e zera quando a
    # ordem completa — quem mostra "quanto trocou" (ticker) lê ESTA coluna.
    executed_quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    filled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)