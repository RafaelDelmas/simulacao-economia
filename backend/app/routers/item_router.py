from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers.item_controller import ItemController
from app.core.auth import get_current_user
from app.core.database import get_db
from app.schemas.item import ItemCreate, ItemOut, ItemUpdate

router = APIRouter(
    prefix="/items",
    tags=["items"],
    dependencies=[Depends(get_current_user)],  # exige login em todas as rotas
)


def get_controller(db: Session = Depends(get_db)) -> ItemController:
    return ItemController(db)


@router.get("", response_model=list[ItemOut])
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    controller: ItemController = Depends(get_controller),
):
    return controller.list(skip=skip, limit=limit)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, controller: ItemController = Depends(get_controller)):
    return controller.get(item_id)


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ItemCreate, controller: ItemController = Depends(get_controller)
):
    return controller.create(payload)


@router.put("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    payload: ItemUpdate,
    controller: ItemController = Depends(get_controller),
):
    return controller.update(item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, controller: ItemController = Depends(get_controller)):
    controller.delete(item_id)
