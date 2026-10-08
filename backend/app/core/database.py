from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


# expire_on_commit=False: os objetos do order book continuam utilizáveis
# depois do commit (senão viram DetachedInstanceError ao serem reordenados).
SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base para todos os models ORM."""


def get_db():
    """Dependency que fornece uma sessão de banco por request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria as tabelas existentes (útil em desenvolvimento)."""
    from app.models import Commodity, Item, Order, User  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Migrações idempotentes de colunas novas (create_all não altera tabela pronta)
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "balance NUMERIC(14,2) NOT NULL DEFAULT 0"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE commodities ADD COLUMN IF NOT EXISTS "
                "is_frozen BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        # Linhas legadas ficam com 0 (a quantidade original se perdeu quando a
        # ordem zerou); ordens novas acumulam certo a cada match.
        conn.execute(
            text(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS "
                "executed_quantity DOUBLE PRECISION NOT NULL DEFAULT 0"
            )
        )
        # Combo de vendas lucrativas (UX): linha legada começa em 0.
        conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "streak INTEGER NOT NULL DEFAULT 0"
            )
        )
    # Sessão ORM para ops de seed (balance admin etc.)
    db = SessionLocal()
    try:
        from app.models.user import User
        admin = db.query(User).filter(User.username == settings.admin_username).first()
        if admin and admin.balance == 0:
            admin.balance = settings.jogo_inicial_saldo
            db.merge(admin)
            db.commit()
    finally:
        db.close()