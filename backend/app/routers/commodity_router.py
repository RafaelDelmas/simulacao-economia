from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers.commodity_controller import CommodityController
from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.commodity import Commodity
from app.models.user import User
from app.schemas.commodity import (
    ClearBookIn,
    CommodityCreate,
    CommodityFreeze,
    CommodityOut,
    CommodityShock,
    CommodityUpdate,
    PricePointOut,
)

router = APIRouter(prefix="/commodities", tags=["commodities"])


def get_controller(db: Session = Depends(get_db)) -> CommodityController:
    return CommodityController(db)


@router.get("", response_model=list[CommodityOut])
def list_commodities(controller: CommodityController = Depends(get_controller)):
    """Lista todas as commodities."""
    return controller.list()


@router.get("/history", response_model=list[PricePointOut])
def price_history(
    limit: int = Query(180, ge=10, le=1000),
    controller: CommodityController = Depends(get_controller),
):
    """Últimas `limit` amostras de preço de cada commodity (alimenta os gráficos)."""
    return controller.history(limit)


@router.post("", response_model=CommodityOut, status_code=status.HTTP_201_CREATED)
def create_commodity(
    payload: CommodityCreate,
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Criar nova commodity — somente admin."""
    return controller.create(payload)


@router.post("/seed")
def seed_defaults(
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Semente 5 commodities padrão se não existirem."""
    controller.seed_defaults()
    return {"detail": "Commodities padronizadas inseridas (se não existissem)"}


@router.post("/refresh-prices")
def refresh_prices(
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Atualiza preços atuais das commodities (chamado pelo engine/loop)."""
    controller.refresh_prices()
    return {"detail": "Preços atualizados"}


# --- intervenções de mercado (admin) --------------------------------------
# Rotas literais antes das parametrizadas, pra nunca serem engolidas.


@router.post("/reset")
def reset_market(
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Zerada geral: cancela todas as ordens abertas e volta os preços ao
    nominal (botão de emergência quando o mercado emperra)."""
    return controller.reset_market()


@router.post("/{commodity_id}/shock")
def shock(
    commodity_id: int,
    payload: CommodityShock,
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Choque de preço: move todas as ordens abertas em ±% (recortado na
    faixa) e atualiza o preço exibido na hora."""
    return controller.shock(commodity_id, payload)


@router.post("/{commodity_id}/clear-book")
def clear_book(
    commodity_id: int,
    payload: ClearBookIn | None = None,
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Cancela todas as ordens abertas da commodity (por padrão volta o
    preço ao nominal). Os bots reabastecem o book em ~100ms."""
    return controller.clear_book(commodity_id, payload)


@router.post("/{commodity_id}/freeze")
def freeze(
    commodity_id: int,
    payload: CommodityFreeze,
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Congela/reabre a commodity: congelada não aceita ordem nova."""
    return controller.set_frozen(commodity_id, payload)


@router.patch("/{commodity_id}", response_model=CommodityOut)
def update_commodity(
    commodity_id: int,
    payload: CommodityUpdate,
    _: User = Depends(get_current_admin),
    controller: CommodityController = Depends(get_controller),
):
    """Troca o preço base (âncora nominal) — o book é recortado na nova
    faixa e o preço exibido acompanha."""
    return controller.set_base_price(commodity_id, payload)