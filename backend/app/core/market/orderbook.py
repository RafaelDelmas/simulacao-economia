"""Order Book simples por commodity: mantém bids (compras) e asks (vendas) ordenados."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Dict, List, Tuple

from app.core.database import SessionLocal
from app.core.market.events import event_bus
from app.models.commodity import Commodity
from app.models.order import Order
from app.models.position import Position
from app.models.user import User

logger = logging.getLogger(__name__)


class OrderBook:
    """Structures: bids e asks por commodity.

    - bids: ordens de compra (higher price first)
    - asks: ordens de venda (lower price first)
    """

    def __init__(self, db_session=None):
        self._bids: Dict[int, List[Order]] = defaultdict(list)  # commodity_id -> bids
        self._asks: Dict[int, List[Order]] = defaultdict(list)  # commodity_id -> asks
        # Sessão opcional; sem injeção, cada persistência cria a sua (thread-safe).
        self._db = db_session
        # Bots (event loop) e API (threadpool) mexem no mesmo book.
        self._lock = threading.RLock()

    @contextmanager
    def locked(self):
        """Mantém o lock do book durante o bloco do caller.

        Exposto pro controller de cancelamento: o delete no banco precisa
        acontecer com o book parado, senão um `_match` (bots a cada 100ms)
        poderia liquidar a ordem entre o SELECT e o DELETE — dinheiro trocaria
        de mão sem linha no banco. Todos os matches rodam sob este lock,
        segurá-lo aqui é o que torna "cancelar" e "executar" mutuamente
        exclusivos. RLock: `remove_ids` pode ser chamado de dentro.
        """
        with self._lock:
            yield

    def add(self, order: Order) -> Tuple[bool, str]:
        """Insere uma ordem e tenta matching imediatos. Retorna (executou_parte, status).

        Toda a mutação do book acontece sob lock: bots rodam no event loop e a
        API em threadpool — sem isso, dois matches simultâneos poderiam perder
        uma atualização de quantidade.
        """
        with self._lock:
            cid = order.commodity_id
            side = order.side

            if side == "bid":
                self._bids[cid].append(order)
                self._bids[cid].sort(key=lambda o: o.price, reverse=True)
            else:
                self._asks[cid].append(order)
                self._asks[cid].sort(key=lambda o: o.price)

            # Attempt immediate match: best bid vs best ask
            executed = self._match(cid, aggressor=order)
            if executed:
                event_bus.publish(
                    "order.executed",
                    {
                        "order_id": getattr(executed, "id", None),
                        "commodity_id": cid,
                        "side": executed.side,
                        "price": executed.price,
                        "quantity": executed.executed_quantity,
                        "filled": executed.filled,
                    },
                )
            return True, "ok"

    def shock_prices(
        self,
        commodity_id: int,
        factor: float,
        floor: float | None = None,
        ceil: float | None = None,
    ) -> list[tuple[int, float]]:
        """Intervenção do admin: move todas as ordens abertas por `factor`.

        - `floor`/`ceil` recortam na faixa nominal (o book nunca sai da regra
          do mundo); com `factor = 1.0` vira só um recorte — é o que o ajuste
          de preço base usa pra acomodar o book na nova faixa.
        - Book cruzado pelo choque é liquidado na hora (senão ficaria esperando
          um `add` de bot pra executar — e commodity congelada não recebe add).
        - Devolve (id, novo_preco) das ordens persistidas; o caller faz o UPDATE
          no banco (o book é a fonte de verdade, o banco é o espelho).
        """
        alteradas: list[tuple[int, float]] = []
        with self._lock:
            for book, reverse in (
                (self._bids, True),
                (self._asks, False),
            ):
                ordens = book.get(commodity_id)
                if not ordens:
                    continue
                mudou = False
                for o in ordens:
                    if o.filled or o.quantity <= 0:
                        continue
                    novo = o.price * factor
                    if floor is not None:
                        novo = max(novo, floor)
                    if ceil is not None:
                        novo = min(novo, ceil)
                    novo = round(max(novo, 0.01), 2)
                    if novo == o.price:
                        continue
                    o.price = novo
                    mudou = True
                    # id lê DEPOIS de mutar: ordem de bot recém-criada pode ainda
                    # não ter id — o commit do bot persiste o preço já mutado.
                    oid = getattr(o, "id", None)
                    if oid is not None:
                        alteradas.append((oid, novo))
                if mudou:
                    ordens.sort(key=lambda o: o.price, reverse=reverse)
            self._settle_crossed(commodity_id)
        return alteradas

    def _settle_crossed(self, commodity_id: int, limit: int = 500) -> None:
        """Executa pares cruzados (bid >= ask) já existentes no book.

        Normalmente o cruzamento resolve sozinho no próximo `add()` de bot, mas
        um choque pode cruzar o book de uma commodity congelada (sem adds).
        `_match` sem aggressor executa no preço do melhor ask (o menor).
        """
        for _ in range(limit):
            bid = self.get_best_bid(commodity_id)
            ask = self.get_best_ask(commodity_id)
            if bid is None or ask is None or bid.price < ask.price:
                return
            if bid.quantity <= 0 or ask.quantity <= 0:
                return  # sanidade: ordem zerada não deveria estar no book
            antes = (bid.quantity, ask.quantity)
            self._match(commodity_id)
            if (bid.quantity, ask.quantity) == antes:
                return  # sem progresso: não rodar o laço pra sempre

    def remove_ids(self, ids: set) -> int:
        """Remove do book as ordens com os ids informados (usado pelo prune).

        Devolve quantas ordens saíram. Ordem sem id (ainda não persistida) nunca
        é removida — o banco também não as enxerga nesse momento.
        """
        if not ids:
            return 0
        with self._lock:
            removidas = 0
            for book in (self._bids, self._asks):
                for cid in list(book):
                    mantidas = [
                        o for o in book[cid] if getattr(o, "id", None) not in ids
                    ]
                    removidas += len(book[cid]) - len(mantidas)
                    if mantidas:
                        book[cid] = mantidas
                    else:
                        del book[cid]  # não acumular listas vazias
            return removidas

    def _apply_fill(
        self, commodity_id: int, qty: float, price: float, bid: Order, ask: Order
    ) -> None:
        """Liquida uma execução: baixa as ordens e move dinheiro + estoque.

        - Comprador paga `qty * price` e recebe `qty` do estoque;
        - Vendedor recebe o dinheiro e entrega `qty` do estoque;
        - Lado de bot (`user_id = None`) não liquida: a tesouraria do sistema
          absorve — é ela que cria/destrói dinheiro no jogo.

        A Session do SQLAlchemy não é segura entre threads (requisições rodam em
        threadpool), então cada liquidação usa a sessão injetada ou cria a sua
        própria e atualiza tudo pela chave primária. `_match` só roda sob o lock
        do book, logo essas escritas acontecem uma por vez.
        """
        sess = self._db or SessionLocal()
        try:
            # 1. ordens: restam quantity / filled
            for order in (bid, ask):
                if order.id is None:
                    continue  # ainda não persistida: o dono faz o commit
                row = sess.get(Order, order.id)
                if row is None:
                    continue
                if (
                    row.quantity != order.quantity
                    or row.filled != order.filled
                    or row.executed_quantity != order.executed_quantity
                ):
                    row.quantity = order.quantity
                    row.filled = order.filled
                    row.executed_quantity = round(order.executed_quantity or 0, 6)

            # 2. liquidação financeira e de estoque
            valor = round(qty * price, 2)
            if ask.user_id is not None:
                # O preço médio precisa ser lido ANTES da baixa do estoque:
                # é o lucro realizado da venda que move o combo 🔥.
                lucro = self._lucro_realizado(
                    sess, ask.user_id, commodity_id, qty, price
                )
                self._bump_balance(sess, ask.user_id, valor)
                self._bump_position(sess, ask.user_id, commodity_id, -qty, price)
                self._bump_streak(sess, ask.user_id, lucro)
            if bid.user_id is not None:
                self._bump_balance(sess, bid.user_id, -valor)
                self._bump_position(sess, bid.user_id, commodity_id, qty, price)

            sess.commit()
        finally:
            if self._db is None:
                sess.close()

    @staticmethod
    def _bump_balance(sess, user_id: int, delta: float) -> None:
        """Soma/subtrai do saldo. Atualização no objeto: a sessão já o mapeia."""
        user = sess.get(User, user_id)
        if user is not None:
            user.balance = round(float(user.balance or 0) + delta, 2)
            if user.balance < -1e-9:
                # Rede de segurança: `_check_trade` na criação deveria ter
                # impedido — loga alto em vez de deixar negativo silencioso.
                logger.warning(
                    "saldo negativo após liquidação: user=%s balance=%s delta=%s",
                    user_id,
                    user.balance,
                    delta,
                )

    @staticmethod
    def _bump_position(
        sess, user_id: int, commodity_id: int, delta: float, price: float
    ) -> None:
        """Atualiza o estoque e o preço médio do usuário nesta commodity."""
        pos = (
            sess.query(Position)
            .filter(Position.user_id == user_id)
            .filter(Position.commodity_id == commodity_id)
            .first()
        )
        if pos is None:
            sess.add(
                Position(
                    user_id=user_id,
                    commodity_id=commodity_id,
                    quantity=round(delta, 6),
                    avg_price=round(price, 4),
                )
            )
            if delta < -1e-9:
                # Sem linha anterior não dá pra ter estoque a entregar:
                # `_check_trade` na criação deveria ter barrado.
                logger.warning(
                    "estoque negativo sem linha anterior: user=%s "
                    "commodity=%s delta=%s",
                    user_id,
                    commodity_id,
                    delta,
                )
            sess.flush()  # a próxima chamada precisa enxergar a linha
            return

        antes = float(pos.quantity or 0)
        novo = round(antes + delta, 6)
        if abs(novo) < 1e-9:
            novo = 0.0
        if delta > 0 and antes <= 0:
            pos.avg_price = round(price, 4)  # abrindo posição (ou cobrindo venda a descoberto)
        elif delta > 0 and novo > 0:
            pos.avg_price = round(
                (float(pos.avg_price or 0) * antes + price * delta) / novo, 4
            )
        elif novo == 0:
            pos.avg_price = 0.0  # zerou a posição
        # venda com estoque positivo: o preço médio de compra permanece
        pos.quantity = novo
        if novo < -1e-9:
            # Rede de segurança (mesma do saldo): a checagem na criação é o
            # muro — aqui só avisamos se algum outro caminho furou.
            logger.warning(
                "estoque negativo após liquidação: user=%s commodity=%s "
                "quantity=%s delta=%s",
                user_id,
                commodity_id,
                novo,
                delta,
            )
        sess.flush()

    @staticmethod
    def _lucro_realizado(
        sess, user_id: int, commodity_id: int, qty: float, price: float
    ) -> float:
        """(preço da venda − preço médio) × qtd, com a posição ainda intacta.

        Só a venda realiza (quem compra não mexe no combo). Posição ausente
        ou média inválida devolve 0.0 — empate, não prejuízo: isso preserva a
        rede de segurança de estoque negativo sem castigar quem vendeu certo.
        """
        pos = (
            sess.query(Position)
            .filter(Position.user_id == user_id)
            .filter(Position.commodity_id == commodity_id)
            .first()
        )
        if pos is None:
            return 0.0
        estoque = float(pos.quantity or 0)
        media = float(pos.avg_price or 0)
        if estoque <= 0 or media <= 0:
            return 0.0
        return round((price - media) * min(qty, estoque), 6)

    @staticmethod
    def _bump_streak(sess, user_id: int, lucro: float) -> None:
        """Combo de vendas lucrativas: lucro +1, prejuízo zera, empate mantém.

        Recompensa quem protege a margem e dói em quem quebra a sequência —
        exibição pura (`users.streak`), nenhuma regra de saldo passa por aqui.
        """
        if abs(lucro) < 1e-9:
            return
        user = sess.get(User, user_id)
        if user is None:
            return
        if lucro > 0:
            user.streak = int(user.streak or 0) + 1
        else:
            user.streak = 0

    def _match(self, commodity_id: int, aggressor: Order | None = None) -> Order | None:
        """Match the best bid vs best ask for a commodity. Returns the order that was executed or None.

        `aggressor` é a ordem recém-inserida (a que cruzou o spread). O preço de
        execução é o da ordem que já estava descansando no book — quem chega
        cruzando leva o melhor preço possível.
        """
        bids = self._bids.get(commodity_id, [])
        asks = self._asks.get(commodity_id, [])

        if not bids or not asks:
            return None

        best_bid = bids[0]  # highest bid
        best_ask = asks[0]  # lowest ask

        if best_bid.price < best_ask.price:
            # Spread: no match
            return None

        # Match at or across the spread
        # Execute quantity min of both
        q = min(best_bid.quantity, best_ask.quantity)
        if q <= 0:
            return None

        # Preço da negociação: o do lado que estava no book antes
        if aggressor is best_bid:
            price = best_ask.price
        elif aggressor is best_ask:
            price = best_bid.price
        else:
            price = min(best_bid.price, best_ask.price)

        # Baixa a quantidade dos dois lados (preenchimento parcial ou total)
        # e acumula o que já executou — `quantity` é o restante (zerada quando
        # completa); quem precisa do "quanto trocou" lê executed_quantity.
        best_bid.quantity -= q
        best_ask.quantity -= q
        best_bid.executed_quantity = round((best_bid.executed_quantity or 0) + q, 6)
        best_ask.executed_quantity = round((best_ask.executed_quantity or 0) + q, 6)

        executed: Order | None = None

        # Se a ordem zerou, marca como preenchida e tira do book
        if best_bid.quantity <= 0:
            best_bid.filled = True
            try:
                self._bids[commodity_id].remove(best_bid)
            except ValueError:
                pass
            executed = best_bid
        if best_ask.quantity <= 0:
            best_ask.filled = True
            try:
                self._asks[commodity_id].remove(best_ask)
            except ValueError:
                pass
            executed = best_ask

        # Persiste as ordens E liquida dinheiro/estoque dos donos
        self._apply_fill(commodity_id, q, price, best_bid, best_ask)

        # Ordem totalmente executada (None se sobrou quantidade)
        return executed

    def get_best_bid(self, commodity_id: int) -> Order | None:
        if not self._bids.get(commodity_id):
            return None
        return self._bids[commodity_id][0]

    def get_best_ask(self, commodity_id: int) -> Order | None:
        if not self._asks.get(commodity_id):
            return None
        return self._asks[commodity_id][0]

    def best_bid_price(self, commodity_id: int) -> float | None:
        ob = self.get_best_bid(commodity_id)
        return ob.price if ob else None

    def best_ask_price(self, commodity_id: int) -> float | None:
        ob = self.get_best_ask(commodity_id)
        return ob.price if ob else None

    def depth(self, commodity_id: int, levels: int = 12) -> dict:
        """Livro de ofertas agregado por preço — o topo real do book em memória.

        Os dois lados já são mantidos ordenados (bids desc, asks asc), então dá
        pra varrer uma vez e cortar nos primeiros níveis.
        """
        def agregar(ordens: List[Order]) -> List[dict]:
            niveis: Dict[float, dict] = {}
            for o in ordens:
                if o.filled or o.quantity <= 0:
                    continue
                nivel = niveis.get(o.price)
                if nivel is None:
                    niveis[o.price] = {
                        "price": o.price,
                        "quantity": round(o.quantity, 6),
                        "orders": 1,
                    }
                else:
                    nivel["quantity"] = round(nivel["quantity"] + o.quantity, 6)
                    nivel["orders"] += 1
            return list(niveis.values())[:levels]

        with self._lock:
            bids = agregar(self._bids.get(commodity_id, []))
            asks = agregar(self._asks.get(commodity_id, []))

        spread = None
        if bids and asks:
            spread = round(asks[0]["price"] - bids[0]["price"], 2)
        return {"bids": bids, "asks": asks, "spread": spread}

    def snapshot(self, commodity_id: int) -> dict:
        """Retorna um dicionado pronto para ser enviado via WS."""
        return {
            "best_bid_price": self.best_bid_price(commodity_id),
            "best_ask_price": self.best_ask_price(commodity_id),
            "open_bids_count": len(self._bids.get(commodity_id, [])),
            "open_asks_count": len(self._asks.get(commodity_id, [])),
        }


# Instância compartilhada: engine, bots, API e WebSocket usam o MESMO book.
order_book = OrderBook()