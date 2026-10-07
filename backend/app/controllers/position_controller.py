from sqlalchemy.orm import Session

from app.models.commodity import Commodity
from app.models.position import Position
from app.schemas.position import PositionOut


class PositionController:
    """Carteira do jogador: estoque por commodity e marcação a mercado."""

    def __init__(self, db: Session):
        self.db = db

    def list_mine(self, user_id: int) -> list[PositionOut]:
        rows = (
            self.db.query(Position, Commodity)
            .join(Commodity, Commodity.id == Position.commodity_id)
            .filter(Position.user_id == user_id)
            .order_by(Position.quantity.desc())
            .all()
        )

        out: list[PositionOut] = []
        for pos, com in rows:
            qty = float(pos.quantity or 0)
            if abs(qty) < 1e-9:
                continue  # posição zerada não interessa na carteira
            preco = float(com.current_price or 0)
            media = float(pos.avg_price or 0)
            valor = round(qty * preco, 2)
            custo = round(qty * media, 2)
            out.append(
                PositionOut(
                    commodity_id=com.id,
                    name=com.name,
                    quantity=round(qty, 6),
                    avg_price=media,
                    current_price=preco,
                    valor=valor,
                    custo=custo,
                    lucro=round(valor - custo, 2),
                )
            )
        return out
