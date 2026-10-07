from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate


class ItemController:
    """Camada de controle: contém as regras de negócio dos itens."""

    def __init__(self, db: Session):
        self.db = db

    def list(self, skip: int = 0, limit: int = 50) -> list[Item]:
        return (
            self.db.query(Item)
            .order_by(Item.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get(self, item_id: int) -> Item:
        item = self.db.get(Item, item_id)
        if not item:
            raise NotFoundError(f"Item {item_id} não encontrado")
        return item

    def create(self, payload: ItemCreate) -> Item:
        item = Item(**payload.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item_id: int, payload: ItemUpdate) -> Item:
        item = self.get(item_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> None:
        item = self.get(item_id)
        self.db.delete(item)
        self.db.commit()
