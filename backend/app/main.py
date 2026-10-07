import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers.user_controller import UserController
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.core.error_handlers import register_exception_handlers
from app.core.market.events import event_bus
from app.core.market.orderbook import order_book
from app.core.market.prune import prune_loop, prune_tudo
from app.routers import health_router, item_router, user_router, commodity_router, order_router, auth_router, position_router

# Logs da aplicação (INFO em diante). Sem isso nada daqui chega ao log do uvicorn.
# O SQLAlchemy loga cada SQL em INFO: sem segurar, o arquivo inundaria.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# `order_book` (app.core.market.orderbook) é a instância compartilhada pelo
# engine de mercado, pelos bots, pela API e pelo WebSocket.


# --- Lifecycle ---
async def _run_market_engine():
    """Sobe o MarketEngine e o BotEngine sobre o mesmo order book."""
    from app.core.market import bots as bt, engine as me

    market_engine = me.MarketEngine(order_book=order_book)
    bot_engine = bt.BotEngine(order_book=order_book)

    market_task = asyncio.create_task(market_engine.start())
    await bot_engine.start()  # o BotEngine cria e guarda o próprio loop interno
    try:
        await market_task
    finally:
        market_engine.running = False
        await bot_engine.stop()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 1. Inicializa DB (tabelas) + seed (commodities + admin balance)
    init_db()

    # 2. Semente de dados iniciais
    from app.controllers.commodity_controller import CommodityController
    from app.models.user import User

    db = SessionLocal()
    try:
        UserController(db).ensure_admin()
        CommodityController(db).seed_defaults()

        admin = db.query(User).filter(User.username == settings.admin_username).first()
        if admin and admin.balance == 0:
            admin.balance = settings.jogo_inicial_saldo
            db.commit()
    finally:
        db.close()

    # 2b. Preços fora da faixa nominal voltam para ela — o book começa vazio,
    #     então ninguém herda preços absurdos de rodadas antigas.
    from app.core.market.engine import clamp_prices

    fora_da_faixa = clamp_prices()
    if fora_da_faixa:
        logger.info("clamp de precos: %s commodities fora da faixa", fora_da_faixa)

    # 3. Prune inicial: corta o histórico e apaga as abertas órfãs de restarts
    #    anteriores (o book começa vazio, logo nenhuma aberta sobrevive a um boot)
    stats = prune_tudo(order_book, limpar_abertas=True)
    logger.info(
        "prune inicial: %s abertas expiradas, %s historicas removidas, "
        "%s ticks removidos | orders total = %s",
        stats["abertas_expiradas"],
        stats["historico_removido"],
        stats["ticks_removidos"],
        stats["orders_total"],
    )

    # 4. Iniciar engine de mercado e o prune periódico em background
    engine_task = asyncio.create_task(_run_market_engine())
    prune_task = asyncio.create_task(prune_loop(order_book))
    try:
        yield
    finally:
        for task in (engine_task, prune_task):
            task.cancel()
        for task in (engine_task, prune_task):
            try:
                await task
            except asyncio.CancelledError:
                pass


# --- App creation ---
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# --- Middleware ---
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rotas API ---
app.include_router(health_router.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(item_router.router, prefix="/api")
app.include_router(user_router.router, prefix="/api")
app.include_router(commodity_router.router, prefix="/api")
app.include_router(order_router.router, prefix="/api")
app.include_router(position_router.router, prefix="/api")


# --- WebSocket market ---
import json
from fastapi import WebSocket


@app.websocket("/ws/market")
async def ws_market(ws: WebSocket):
    """WebSocket que transmite preços, ordens e impostos em tempo real."""
    await ws.accept()
    handlers = {
        "market.tick": lambda data: _ws_send_json(ws, data),
        "tax.applied": lambda data: _ws_send_json(ws, data),
        "bot.activity": lambda data: _ws_send_json(ws, data),
    }
    try:
        # Assina os eventos (guardamos os handlers para desinscrever depois)
        for event_type, handler in handlers.items():
            event_bus.subscribe(event_type, handler)

        # Envia snapshot inicial
        await ws.send_json({"type": "init", "snapshot": order_book.snapshot(0)})

        # Mantém conexão aberta; o fluxo é server -> client
        while True:
            await ws.receive()
    except Exception:
        pass
    finally:
        for event_type, handler in handlers.items():
            event_bus.unsubscribe(event_type, handler)


def _ws_send_json(ws: WebSocket, data: dict):
    """Agenda o envio de JSON — o event bus é síncrono e `send_text` é async."""
    try:
        asyncio.get_running_loop().create_task(_send_json(ws, data))
    except RuntimeError:  # fora do event loop (não deve acontecer)
        pass


async def _send_json(ws: WebSocket, data: dict):
    try:
        await ws.send_text(json.dumps(data, default=str))
    except Exception:
        pass  # conexão já fechada
