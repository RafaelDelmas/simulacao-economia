from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.market.orderbook import order_book
from app.models.commodity import Commodity
from app.models.order import Order
from app.models.position import Position
from app.models.user import User
from app.schemas.order import MyOrdersOut, OrderCreate, OrderOut


class OrderController:
    """Camada de controle: gestão de ordens no order book."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: OrderCreate, user_id: int | None = None) -> OrderOut:
        # Verifica se a commodity existe
        commodity = self.db.get(Commodity, payload.commodity_id)
        if commodity is None:
            raise NotFoundError(f"Commodity {payload.commodity_id} não encontrada")

        # Congelada pelo admin: mercado suspenso, sem ordem nova (nem de bot —
        # o bot engine também filtra; aqui é a porta de entrada do jogador)
        if commodity.is_frozen:
            raise ConflictError(
                f"{commodity.name} está suspenso pelo admin — mercado fechado"
            )

        order = Order(
            commodity_id=payload.commodity_id,
            user_id=user_id,
            side=payload.side,
            quantity=payload.quantity,
            executed_quantity=0.0,
            price=payload.price,
            filled=False,
        )

        # Checagens + insert + entrada no book no MESMO lock: sem isso, duas
        # requisições paralelas enxergam os mesmos números e passam juntas
        # (11ª ordem ou saldo/estoque estourado), e um `_match` poderia
        # liquidar entre a checagem e o insert. É o lock do match (serializa
        # criar × casar) e do cancel (serializa criar × cancelar).
        with order_book.locked():
            if user_id is not None:
                # Regra do jogo: só compra quem tem saldo, só vende quem tem
                # estoque — descontando o já comprometido nas abertas
                self._check_trade(user_id, commodity, payload)
                self._check_limit(user_id)
            self.db.add(order)
            self.db.commit()
            self.db.refresh(order)
            # Entra no order book em memória para participar do matching
            order_book.add(order)
        return OrderOut.model_validate(order)

    def _check_limit(self, user_id: int) -> None:
        """Barra a (n+1)-ésima ordem aberta do jogador.

        Limite global (todas as commodities juntas), contado com o mesmo
        predicado do `list_mine` (blindagem contra dado legado). Precisa ser
        chamada sob `order_book.locked()` — aí a contagem e o insert seguinte
        são atômicos. Bots não passam por aqui (criam ordem direto no book,
        com `user_id = None`).
        """
        limite = max(1, settings.jogador_ordens_abertas_max)
        abertas = (
            self.db.query(func.count(Order.id))
            .filter(Order.user_id == user_id)
            .filter(Order.filled == False, Order.quantity > 0)
            .scalar()
            or 0
        )
        if abertas >= limite:
            raise ConflictError(
                f"Limite de {limite} ordens abertas atingido — "
                "cancele uma (✖ na carteira) antes de criar outra"
            )

    def cancel(self, order_id: int, user: User) -> None:
        """Cancela uma ordem aberta: do próprio jogador, ou de qualquer uma (admin).

        - Tudo sob o lock do book (`order_book.locked()`): `_match` roda no
          mesmo lock, então não existe "cancelar enquanto executa".
        - Sem estorno: saldo/estoque só trocam no match, nunca na criação —
          cancelar é só tirar do book e apagar a linha (mesma coisa que o
          prune faz com as expiradas; `filled = false` volta a ⟺ viva no book).
        - Execução parcial antes do cancel fica: o que já executou liquidou
          de verdade; o que restava some.
        - Mercado congelado cancela sim — o freeze bloqueia ordem nova,
          nunca retirada.
        - Ordem de bot (`user_id = None`) só o admin alcança.
        """
        with order_book.locked():
            row = self.db.get(Order, order_id)
            # 404 tanto pra id inexistente quanto pra ordem alheia: não vaza
            # pro jogador a existência de ordem de outro usuário.
            if row is None or (row.user_id != user.id and not user.is_admin):
                raise NotFoundError("Ordem não encontrada")
            if row.filled or row.quantity <= 0:
                # executou entre o list e o cancel — o book já nem a tem
                raise ConflictError("Ordem já executada")
            self.db.delete(row)
            self.db.commit()
            order_book.remove_ids({order_id})

    def _check_trade(
        self, user_id: int, commodity: Commodity, payload: OrderCreate
    ) -> None:
        """Barra ordem que o jogador não tem condição de honrar.

        O saldo/estoque "livre" desconta o comprometido nas ordens abertas do
        jogador (`filled = false AND quantity > 0`): sem isso, duas vendas de
        1 un passariam cada uma checando contra o MESMO estoque de 1 e o
        segundo match deixaria o estoque negativo — saldo tem o mesmo furo.
        Comprometido: compras batem no saldo (um saldo só, qualquer commodity);
        vendas batem no estoque (só daquela commodity).
        Precisa rodar sob `order_book.locked()` — aí a checagem é atômica
        contra `_apply_fill` e contra outra criação paralela.
        """
        user = self.db.get(User, user_id)
        if user is None:
            return

        if payload.side == "bid":
            comprometido = float(
                self.db.query(
                    func.coalesce(func.sum(Order.quantity * Order.price), 0.0)
                )
                .filter(Order.user_id == user_id, Order.side == "bid")
                .filter(Order.filled == False, Order.quantity > 0)
                .scalar()
                or 0.0
            )
            necessario = round(payload.quantity * payload.price, 2)
            disponivel = float(user.balance or 0) - comprometido
            extra = (
                f" — {comprometido:.2f} já em compras abertas"
                if comprometido > 1e-9
                else ""
            )
            if necessario > disponivel + 1e-9:
                raise ConflictError(
                    f"Saldo insuficiente para esta compra "
                    f"(livre {disponivel:.2f}, necessário {necessario:.2f}){extra}"
                )
        else:
            comprometido = float(
                self.db.query(func.coalesce(func.sum(Order.quantity), 0.0))
                .filter(Order.user_id == user_id, Order.side == "ask")
                .filter(Order.commodity_id == commodity.id)
                .filter(Order.filled == False, Order.quantity > 0)
                .scalar()
                or 0.0
            )
            pos = (
                self.db.query(Position)
                .filter(Position.user_id == user_id)
                .filter(Position.commodity_id == commodity.id)
                .first()
            )
            estoque = float(pos.quantity) if pos is not None else 0.0
            livre = estoque - comprometido
            extra = (
                f" — {comprometido:g} un já em vendas abertas"
                if comprometido > 1e-9
                else ""
            )
            if payload.quantity > livre + 1e-9:
                raise ConflictError(
                    f"Estoque insuficiente de {commodity.name} "
                    f"(livre {livre:g}, oferta {payload.quantity:g}){extra}"
                )

    def list_mine(self, user_id: int) -> MyOrdersOut:
        """Ordens do jogador: abertas (no book) e já executadas."""
        base = self.db.query(Order).filter(Order.user_id == user_id)
        abertas = (
            base.filter(Order.filled == False, Order.quantity > 0)
            .order_by(Order.created_at.desc())
            .limit(100)
            .all()
        )
        executadas = (
            base.filter(Order.filled == True)
            .order_by(Order.created_at.desc())
            .limit(100)
            .all()
        )
        return MyOrdersOut(
            open=[OrderOut.model_validate(r) for r in abertas],
            filled=[OrderOut.model_validate(r) for r in executadas],
        )

    def list_open(self, commodity_id: int | None = None, limit: int = 200) -> list[OrderOut]:
        # quantity > 0: ordem zerada não é aberta (blindagem contra dados legados)
        q = self.db.query(Order).filter(Order.filled == False, Order.quantity > 0)
        if commodity_id is not None:
            q = q.filter(Order.commodity_id == commodity_id)
        rows = q.order_by(Order.created_at.desc()).limit(limit).all()
        return [OrderOut.model_validate(r) for r in rows]

    def list_filled(self, commodity_id: int | None = None, limit: int = 200) -> list[OrderOut]:
        q = self.db.query(Order).filter(Order.filled == True)
        if commodity_id is not None:
            q = q.filter(Order.commodity_id == commodity_id)
        rows = q.order_by(Order.created_at.desc()).limit(limit).all()
        return [OrderOut.model_validate(r) for r in rows]
