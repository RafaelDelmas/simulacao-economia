from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Commodity(Base):
    """Commodity do mercado (Carvão, Aço, Trigo, Algodão, Café etc.)."""

    __tablename__ = "commodities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_price: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    current_price: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    variation_24h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Congelada pelo admin: sem novas ordens (jogadores e bots) até reabrir.
    is_frozen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )