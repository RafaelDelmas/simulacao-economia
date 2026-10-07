from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError


def register_exception_handlers(app) -> None:
    """Mapeia erros de aplicação para respostas HTTP padronizadas."""

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )
