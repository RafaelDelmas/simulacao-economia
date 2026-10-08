from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.produtoras_controller import ProdutorasController
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.produtoras import ProdutoraComprar

router = APIRouter(prefix="/produtoras", tags=["produtoras"])


def get_controller(db: Session = Depends(get_db)) -> ProdutorasController:
    return ProdutorasController(db)


@router.get("")
def estado(
    user: User = Depends(get_current_user),
    controller: ProdutorasController = Depends(get_controller),
):
    """Catálogo de produtoras (por commodity) + as minhas, com energia/cap/dia."""
    return controller.estado(user.id)


@router.post("/comprar")
def comprar(
    payload: ProdutoraComprar,
    user: User = Depends(get_current_user),
    controller: ProdutorasController = Depends(get_controller),
):
    """Compra a produtora de uma commodity (uma por commodity por jogador)."""
    return controller.comprar(user.id, payload)


@router.post("/{producer_id}/produzir")
def produzir(
    producer_id: int,
    user: User = Depends(get_current_user),
    controller: ProdutorasController = Depends(get_controller),
):
    """Um clique: produz um lote (coba insumo + energia + cap diário)."""
    return controller.produzir(user.id, producer_id)


@router.post("/{producer_id}/melhorar")
def melhorar(
    producer_id: int,
    user: User = Depends(get_current_user),
    controller: ProdutorasController = Depends(get_controller),
):
    """Sobe um nível (custo escalonado; nível máximo do produtoras.json)."""
    return controller.melhorar(user.id, producer_id)
