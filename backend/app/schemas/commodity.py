from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommodityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    base_price: float = Field(100.0, ge=0)


class CommodityCreate(CommodityBase):
    pass


class CommodityOut(CommodityBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_price: float
    variation_24h: float
    is_frozen: bool = False
    created_at: datetime


# --- intervenções de admin -------------------------------------------------


class CommodityUpdate(BaseModel):
    """Muda o preço base (a âncora nominal) da commodity."""

    base_price: float = Field(..., gt=0, le=1_000_000)


class CommodityShock(BaseModel):
    """Empurra todas as ordens abertas da commodity em ±percent (%)."""

    percent: float = Field(..., ge=-95, le=95)


class CommodityFreeze(BaseModel):
    """Congela (True) ou reabre (False) a commodity para novas ordens."""

    frozen: bool = True


class ClearBookIn(BaseModel):
    """Limpa o book da commodity; por padrão leva o preço de volta ao nominal."""

    reset_price: bool = True


class PricePointOut(BaseModel):
    """Amostra de preço para o gráfico (agrupada por commodity no cliente)."""

    commodity_id: int
    price: float
    created_at: datetime