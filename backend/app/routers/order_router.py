from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.core.auth import get_current_admin, get_current_user
from app.core.database import get_db
from app.core.market.orderbook import order_book
from app.core.market.prune import prune_tudo
from app.models.user import User
from app.schemas.order import MyOrdersOut, OrderCreate, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


def get_controller(db: Session = Depends(get_db)) -> OrderController:
    return OrderController(db)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    user: User = Depends(get_current_user),
    controller: OrderController = Depends(get_controller),
):
    """Criar uma nova ordem no order book (registra no usuário logado)."""
    return controller.create(payload, user_id=user.id)


@router.get("/mine", response_model=MyOrdersOut)
def list_my_orders(
    user: User = Depends(get_current_user),
    controller: OrderController = Depends(get_controller),
):
    """Ordens do jogador logado: abertas (no book) e já executadas."""
    return controller.list_mine(user.id)


@router.get("/book")
def order_book_depth(
    commodity_id: int = Query(..., ge=1),
    depth: int = Query(12, ge=1, le=50),
):
    """Livro de ofertas de uma commodity (topo real do book em memória)."""
    return order_book.depth(commodity_id, depth)


@router.get("/open", response_model=list[OrderOut])
def list_open_orders(
    commodity_id: int = 0,
    limit: int = Query(200, ge=1, le=1000),
    controller: OrderController = Depends(get_controller),
):
    """Lista ordens abertas (não preenchidas), mais recentes primeiro."""
    return controller.list_open(commodity_id if commodity_id > 0 else None, limit=limit)


@router.get("/filled", response_model=list[OrderOut])
def list_filled_orders(
    commodity_id: int = 0,
    limit: int = Query(200, ge=1, le=1000),
    controller: OrderController = Depends(get_controller),
):
    """Lista ordens preenchidas, mais recentes primeiro."""
    return controller.list_filled(commodity_id if commodity_id > 0 else None, limit=limit)


@router.post("/prune")
def prune_now(_: User = Depends(get_current_admin)):
    """Roda um ciclo de prune agora — mesma regra do loop automático (admin)."""
    return prune_tudo(order_book)


# Parametrizada por último: rotas literais (/mine, /book, /open, /filled,
# /prune) vêm antes, convenção do AGENTS.md.
@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_order(
    order_id: int,
    user: User = Depends(get_current_user),
    controller: OrderController = Depends(get_controller),
):
    """Cancela uma ordem aberta: a do jogador logado, ou qualquer uma (admin).

    404 se não existir / não for sua; 409 se já executou. Sem estorno —
    dinheiro e estoque só trocam no match.
    """
    controller.cancel(order_id, user)