from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """Usuário do sistema. Apenas o admin cria novos usuários."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    balance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
