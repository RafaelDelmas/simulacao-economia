from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.market.orderbook import order_book
from app.core.security import hash_password, verify_password
from app.models.order import Order
from app.models.position import Position
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserController:
    """Camada de controle: regras de autenticação e gestão de usuários."""

    def __init__(self, db: Session):
        self.db = db

    # --- autenticação -------------------------------------------------

    def authenticate(self, username: str, password: str) -> User:
        user = (
            self.db.query(User).filter(User.username == username).first()
        )
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Usuário ou senha inválidos")
        if not user.is_active:
            raise UnauthorizedError("Usuário inativo")
        return user

    # --- usuários -----------------------------------------------------

    def list(self) -> list[User]:
        return self.db.query(User).order_by(User.id.asc()).all()

    def get(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFoundError("Usuário não encontrado")
        return user

    def create(self, payload: UserCreate) -> User:
        """Criação de usuários é exclusiva do administrador (validado na rota)."""
        exists = self.db.query(User).filter(User.username == payload.username).first()
        if exists:
            raise ConflictError(f"Usuário '{payload.username}' já existe")

        user = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            is_admin=payload.is_admin,
            is_active=True,
            # Saldo de partida: o informado pelo admin ou o padrão do .env
            # (`jogo_inicial_saldo`) — sem dinheiro inicial não dá pra jogar.
            balance=(
                payload.balance
                if payload.balance is not None
                else settings.jogo_inicial_saldo
            ),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_balance(self, user_id: int, payload: UserUpdate) -> User:
        """Intervenção do admin no dinheiro: define o saldo final OU soma/
        desconta (bônus, multa, correção de erro de teste)."""
        if payload.balance is None and payload.delta is None:
            raise AppError("Informe balance (valor final) ou delta (variação)")
        user = self.get(user_id)
        if payload.balance is not None:
            novo = round(float(payload.balance), 2)
        else:
            novo = round(float(user.balance or 0) + float(payload.delta), 2)
        if novo < 0:
            raise ConflictError("O saldo não pode ficar negativo")
        user.balance = novo
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user_id: int, actor: User) -> dict:
        """Apaga o jogador do mundo: ordens abertas são canceladas, o estoque
        some e o saldo sai de circulação. As trocas já executadas ficam no
        histórico do mercado com `user_id = NULL` (viram ordens de sistema)."""
        user = self.get(user_id)
        if user.id == actor.id:
            raise ConflictError("Você não pode apagar a própria conta")
        if user.is_admin:
            admins = (
                self.db.query(User).filter(User.is_admin.is_(True)).count()
            )
            if admins <= 1:
                raise ConflictError("Não dá pra apagar o último administrador")

        # 1. ordens abertas saem do banco e do book em memória (senão viram
        #    ordens de sistema e continuariam negociando pelo jogador sumido)
        abertas = [
            r[0]
            for r in self.db.query(Order.id)
            .filter(Order.user_id == user_id, Order.filled.is_(False))
            .all()
        ]
        if abertas:
            self.db.query(Order).filter(Order.id.in_(abertas)).delete(
                synchronize_session=False
            )

        # 2. estoque (o FK de positions já é CASCADE, mas apagamos explícito
        #    pra não depender do estado da constraint no banco)
        estoques = (
            self.db.query(Position)
            .filter(Position.user_id == user_id)
            .delete(synchronize_session=False)
        )

        # 3. trocas executadas ficam, só perdem o dono
        self.db.query(Order).filter(Order.user_id == user_id).update(
            {"user_id": None}, synchronize_session=False
        )

        # 4. a conta — o saldo some junto (é um jogo, o dinheiro sai do mundo)
        username = user.username
        self.db.delete(user)
        self.db.commit()

        if abertas:
            order_book.remove_ids(set(abertas))
        return {
            "detail": f"{username} saiu do jogo",
            "ordens_canceladas": len(abertas),
            "estoques_removidos": int(estoques or 0),
        }

    def ensure_admin(self) -> User:
        """Garante que o usuário admin padrão (do .env) exista no banco."""
        admin = self.db.query(User).filter(User.username == settings.admin_username).first()
        if admin is None:
            admin = User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
                is_active=True,
            )
            self.db.add(admin)
            self.db.commit()
            self.db.refresh(admin)
        return admin
