from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health(db: Session = Depends(get_db)):
    """Endpoint de saúde + verificação de conexão com o banco."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # pragma: no cover
        database = f"error: {exc.__class__.__name__}"

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "database": database,
    }
