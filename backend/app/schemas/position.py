from pydantic import BaseModel


class PositionOut(BaseModel):
    """Linha da carteira do jogador: estoque + marcação a mercado."""

    commodity_id: int
    name: str
    quantity: float
    avg_price: float
    current_price: float
    valor: float       # quantity * current_price
    custo: float       # quantity * avg_price (o que foi pago)
    lucro: float       # valor - custo
