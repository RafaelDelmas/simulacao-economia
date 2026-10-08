"""Prune da tabela `orders`.

É um jogo, não sistema contábil: não faz sentido guardar histórico infinito.
Duas regras aplicadas juntas, deixando o banco com tamanho previsível:

1. **Ordens abertas expiram** (TTL por dono):
   - **bot** (`user_id IS NULL`, `ordem_ttl_minutos` = 5 min): liquidez velha
     atrapalha mais do que ajuda e os bots reabastecem a cada 100ms;
   - **jogador** (`user_id IS NOT NULL`, `ordem_ttl_jogador_minutos` = 10 h):
     tempo de esperar o mercado — e dá pra cancelar antes
     (`DELETE /api/orders/{id}`).
   No prazo, a ordem sai do banco *e* do book em memória. O book zera a cada
   restart, então o **boot apaga todas as abertas** de uma vez
   (`limpar_abertas=True`) em vez de esperar o TTL.
   **Invariante: `filled = false` ⟺ ordem viva no book.**
2. **Histórico de negociações limitado** (`historico_commodities_max`): ficam só
   as últimas N ordens preenchidas de cada commodity — o bastante pra feed de
   trades e pra sensação de preço recente.

O loop roda a cada `prune_intervalo_segundos`; o boot executa um ciclo antes de
subir os engines (assim um restart já começa com a base limpa).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.market.orderbook import OrderBook

logger = logging.getLogger(__name__)

# Abertas além do TTL — cutoff por dono (bot 5 min / jogador 10 h): sai do
# banco e os ids devolvidos sincronizam o book.
_SQL_EXPIRAR_ABERTAS = text(
    """
    DELETE FROM orders
    WHERE filled = false
      AND (   (user_id IS NULL     AND created_at < :cutoff_bot)
           OR (user_id IS NOT NULL AND created_at < :cutoff_jogador))
    RETURNING id
    """
)

# Boot: o book começa vazio, então NENHUMA aberta pode estar viva.
_SQL_ABRIRAS_TODAS = text(
    """
    DELETE FROM orders
    WHERE filled = false
    RETURNING id
    """
)

# Mantém só as últimas `keep` ordens preenchidas de cada commodity.
_SQL_LIMITAR_HISTORICO = text(
    """
    WITH ranked AS (
        SELECT id,
               row_number() OVER (
                   PARTITION BY commodity_id ORDER BY id DESC
               ) AS rn
        FROM orders
        WHERE filled = true
    )
    DELETE FROM orders
    WHERE id IN (SELECT id FROM ranked WHERE rn > :keep)
    """
)


# Mantém só as últimas `keep` amostras de preço de cada commodity (gráficos).
_SQL_LIMITAR_TICKS = text(
    """
    WITH ranked AS (
        SELECT id,
               row_number() OVER (
                   PARTITION BY commodity_id ORDER BY id DESC
               ) AS rn
        FROM price_ticks
    )
    DELETE FROM price_ticks
    WHERE id IN (SELECT id FROM ranked WHERE rn > :keep)
    """
)


def prune_orders(order_book: OrderBook, *, limpar_abertas: bool = False) -> dict:
    """Executa um ciclo de prune. Seguro para chamar de qualquer thread.

    `limpar_abertas=True` apaga TODAS as ordens abertas — uso restrito ao boot,
    onde o book acabou de ser criado e nenhuma ordem pode estar viva.
    """
    # Dois cortes a partir do mesmo "agora": bot (5 min) e jogador (10 h).
    agora = datetime.now(timezone.utc)
    cutoff_bot = agora - timedelta(minutes=max(1, settings.ordem_ttl_minutos))
    cutoff_jogador = agora - timedelta(
        minutes=max(1, settings.ordem_ttl_jogador_minutos)
    )
    keep = max(1, settings.historico_commodities_max)

    sess = SessionLocal()
    try:
        # 1. abertas: fora do TTL do respectivo dono (ou todas, no boot)
        if limpar_abertas:
            expiradas = sess.execute(_SQL_ABRIRAS_TODAS).fetchall()
        else:
            expiradas = sess.execute(
                _SQL_EXPIRAR_ABERTAS,
                {"cutoff_bot": cutoff_bot, "cutoff_jogador": cutoff_jogador},
            ).fetchall()

        # 2. limita o histórico de preenchidas
        historico = sess.execute(
            _SQL_LIMITAR_HISTORICO, {"keep": keep}
        ).rowcount

        sess.commit()

        # 3. sincroniza o book com o que saiu do banco
        book = order_book.remove_ids({row[0] for row in expiradas})

        total = sess.execute(text("SELECT count(*) FROM orders")).scalar_one()
        return {
            "abertas_expiradas": len(expiradas),
            "historico_removido": int(historico),
            "book_sincronizado": book,
            "orders_total": int(total),
        }
    finally:
        sess.close()


def prune_price_history() -> dict:
    """Limita o histórico de preços ao que cabe no gráfico."""
    sess = SessionLocal()
    try:
        removidos = sess.execute(
            _SQL_LIMITAR_TICKS, {"keep": max(10, settings.historico_precos_max)}
        ).rowcount
        sess.commit()
        return {"ticks_removidos": int(removidos)}
    finally:
        sess.close()


def prune_tudo(order_book: OrderBook, *, limpar_abertas: bool = False) -> dict:
    """Um ciclo completo de manutenção: ordens (abertas + histórico) e preços."""
    stats = prune_orders(order_book, limpar_abertas=limpar_abertas)
    stats.update(prune_price_history())
    return stats


async def prune_loop(order_book: OrderBook) -> None:
    """Roda `prune_orders` periodicamente, sem travar o event loop."""
    intervalo = max(5, settings.prune_intervalo_segundos)
    while True:
        await asyncio.sleep(intervalo)
        try:
            stats = await asyncio.to_thread(prune_tudo, order_book)
        except Exception:
            logger.exception("prune falhou")  # nunca engolir erro
            continue
        logger.info(
            "prune: %s abertas expiradas, %s historicas removidas "
            "(book -%s), %s ticks removidos | orders total = %s",
            stats["abertas_expiradas"],
            stats["historico_removido"],
            stats["book_sincronizado"],
            stats["ticks_removidos"],
            stats["orders_total"],
        )
