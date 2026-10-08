"""Posição (estoque + preço médio) — fonte única da fórmula.

Por que existe separado do `OrderBook._bump_position`: a produção das
produtoras também credita estoque, e o preço médio (base do P&L da
carteira) precisa seguir EXATAMENTE a mesma regra do book — dois
cálculos iguais em arquivos diferentes é como nasce bug de contabilidade.

Regras (idênticas às do book desde sempre):
- abre posição (ou cobre venda a descoberto) com `avg_price` = preço novo;
- compra com estoque positivo: média ponderada `(média * antes + preço *
  delta) / novo`;
- zerou a posição: `avg_price = 0`;
- venda com estoque positivo: a média de COMPRA permanece.

Delta < 0 (venda) sem linha anterior loga warning — a checagem na criação
da ordem (`_check_trade`) é o muro; aqui só avisamos se algo furou.
"""

import logging

from app.models.position import Position

logger = logging.getLogger(__name__)


def bump_position(
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
        pos.avg_price = round(price, 4)  # abrindo posição
    elif delta > 0 and novo > 0:
        pos.avg_price = round(
            (float(pos.avg_price or 0) * antes + price * delta) / novo, 4
        )
    elif novo == 0:
        pos.avg_price = 0.0  # zerou a posição
    # venda com estoque positivo: o preço médio de compra permanece
    pos.quantity = novo
    if novo < -1e-9:
        logger.warning(
            "estoque negativo após liquidação: user=%s commodity=%s "
            "quantity=%s delta=%s",
            user_id,
            commodity_id,
            novo,
            delta,
        )
    sess.flush()
