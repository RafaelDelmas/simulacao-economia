from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["Item 1"])
    description: str | None = Field(None, max_length=500)
    value: float = Field(0.0, ge=0, examples=[10.5])


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    value: float | None = Field(None, ge=0)


class ItemOut(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
