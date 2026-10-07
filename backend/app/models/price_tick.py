from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PriceTick(Base):
    """Amostra periódica do preço de uma commodity — alimenta os gráficos.

    O engine grava uma amostra a cada `preco_tick_segundos` e o prune mantém só
    as últimas `historico_precos_max` por commodity (banco com tamanho previsível).
    """

    __tablename__ = "price_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    commodity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("commodities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
