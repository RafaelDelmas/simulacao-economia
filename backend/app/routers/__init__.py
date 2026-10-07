"""Camada de routers (rotas HTTP)."""
from app.routers import (
    auth_router,
    commodity_router,
    health_router,
    item_router,
    order_router,
    position_router,
    user_router,
)

__all__ = [
    "auth_router",
    "commodity_router",
    "health_router",
    "item_router",
    "order_router",
    "position_router",
    "user_router",
]
