from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Position(Base):
    """Estoque de uma commodity de um usuário (o "quanto eu tenho")."""

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "commodity_id", name="uq_positions_user_commodity"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commodity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("commodities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Preço médio de compra — base do lucro/prejuízo exibido na carteira.
    avg_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
