from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Producer(Base):
    """Produtora de uma commodity de um jogador (clicker de estoque).

    Uma por commodity (`UNIQUE user_id + commodity_id`); progride por
    `nivel` (1..5, ver `produtoras.json`). O estoque produzido entra na
    `positions` com preço médio = custo dos insumos (P&L honesto).
    """

    __tablename__ = "producers"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "commodity_id", name="uq_producers_user_commodity"
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
    nivel: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Energia corrente + quando foi pela última vez sincronizada: a
    # regeneração é lazily compensada no ler (sem loop por produtora).
    energia: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    energia_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Último clique: base do cooldown servidor (~1 s, anti-macro).
    ultimo_clique_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Âncora do "dia de jogo": manutenção cobrada e cap zerado por aqui.
    ciclo_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    producao_dia: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    # False = inadimplente (não pagou a manutenção): parada até quitar.
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    divida: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
