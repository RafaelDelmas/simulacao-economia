# AGENTS.md

Guia para agentes/IA que forem editar este repositório.
Documentação voltada ao usuário/uso do sistema: [`README.md`](README.md).

## Visão geral

Simulação econômica multiusuário (mercado de commodities com bots):

| Serviço   | Tecnologia                    | Porta |
|-----------|-------------------------------|-------|
| Backend   | FastAPI + SQLAlchemy + PostgreSQL | 3100  |
| Frontend  | React 18 + Vite 6 (PWA)       | 3200  |
| Database  | PostgreSQL 16 (só em Docker)  | 5432  |

Stack do backend (pinado em `backend/requirements.txt`, Python 3.12):
`fastapi 0.115`, `uvicorn 0.34`, `sqlalchemy 2.0`, `psycopg2-binary`, `pydantic 2.10` +
`pydantic-settings`, `bcrypt`, `PyJWT`, `orjson`, `numpy`.

## Estrutura

```
.
├── docker-compose.yml        # db + backend + frontend (volume postgres_data)
├── .env                      # usado pelo compose (gitignored)
├── backend/
│   ├── Dockerfile            # multi-stage, python:3.12-slim, porta 3100
│   ├── requirements.txt      # versões pinadas — não "atualize por default"
│   └── app/
│       ├── main.py           # app, CORS, lifespan (seed + engines), rotas, WS
│       ├── core/
│       │   ├── config.py         # Settings (pydantic-settings, env_file=".env")
│       │   ├── database.py       # engine, SessionLocal, get_db, init_db
│       │   ├── security.py       # bcrypt + JWT (HS256)
│       │   ├── auth.py           # get_current_user / get_current_admin
│       │   ├── exceptions.py     # AppError e subclasses (404/409/401/403)
│       │   ├── error_handlers.py # AppError -> JSON {"detail": ...}
│       │   └── market/           # orderbook, engine, bots, events, taxes
│       ├── routers/          # camada HTTP (validação + status code)
│       ├── controllers/      # regras de negócio
│       ├── models/           # SQLAlchemy (tabelas)
│       └── schemas/          # Pydantic (DTOs de entrada/saída)
└── frontend/
    ├── vite.config.js        # proxy /api -> http://localhost:3100
    ├── nginx.conf            # em produção: proxy /api -> http://backend:3100
    └── src/
        ├── App.jsx           # shell, abas (mercado/carteira/admin), polling
        ├── api.js            # fetch + Bearer (getJSON/postJSON/patchJSON/delJSON)
        ├── styles.css        # tema dark, mobile-first
        └── components/       # Login, Market, Commodity, Portfolio, Users,
                              # AdminMarket, Chart (PriceChart/Sparkline)
```

**Arquitetura em camadas:** `router (HTTP) → controller (regra) → model/schema (dados)`.

Para criar um recurso novo: `models/<x>.py` → `schemas/<x>.py` →
`controllers/<x>_controller.py` → `routers/<x>_router.py` → registrar o router
em `app/main.py` e exportar o model em `app/models/__init__.py`.

## Comandos

```bash
# --- Tudo em Docker ---
docker compose up --build -d
docker compose logs -f backend

# --- Só o DB em Docker + backend local (cenário de desenvolvimento) ---
docker compose up -d db
cd backend
python3.12 -m venv .venv                 # se faltar python3-venv: use uv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3100

# --- Frontend local (faz proxy de /api para :3100) ---
cd frontend && npm install && npm run dev    # http://localhost:3200

# --- Cenário deste projeto em WSL/Ubuntu (o usado no dia a dia) ---
docker compose up -d db    # só o Postgres em container (simulacao-db, :5432)
cd ~/simulacao-economia/backend && .venv/bin/python -m uvicorn \
  app.main:app --host 0.0.0.0 --port 3100 --reload
# node SÓ via nvm (v20.20.0); npm run dev morre entre invocações não interativas:
cd ~/simulacao-economia/frontend && source ~/.nvm/nvm.sh && \
  ./node_modules/.bin/vite --host 0.0.0.0 --port 3200
# deixar um dev server vivo fora da sessão (log em /tmp):
setsid nohup ./node_modules/.bin/vite --host 0.0.0.0 --port 3200 \
  > /tmp/simulacao-frontend.log 2>&1 &
# matar depois (o padrão precisa ser quebrado, senão o pkill mata o próprio shell):
pkill -f 'uvicor[n]'   # backend
pkill -f 'vit[e]'      # frontend
```

- Em WSL/Ubuntu o `python3 -m venv` costuma falhar (*ensurepip is not available*).
  Alternativa sem `sudo`: `curl -LsSf https://astral.sh/uv/install.sh | sh` e depois
  `~/.local/bin/uv venv --clear --python python3.12 .venv`.
- Para desenvolvimento use `--reload` (`uvicorn app.main:app --reload --port 3100`);
  sem ele, reinicie o processo depois de editar código.
- O backend lê `.env` do **diretório de trabalho** (`env_file=".env"`). Rodando de
  `backend/` não existe `.env` → valem os defaults de `config.py`, que coincidem com
  o `.env.example`. As variáveis do backend são `DB_HOST/DB_PORT/DB_NAME/DB_USER/
  DB_PASSWORD` (não `POSTGRES_*` — essas são do compose).

## Verificação rápida

```bash
curl -s http://localhost:3100/api/health          # {"status":"ok","database":"ok"}
curl -s -X POST http://localhost:3100/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}'    # devolve access_token

TOKEN=$(curl -s -X POST http://localhost:3100/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:3100/api/users
curl -s http://localhost:3100/api/commodities
```

Não há testes automatizados no repositório. Se for criar, prefira
`backend/tests/` com `pytest` + `fastapi.testclient` (o `TestClient` dispara o
lifespan, então valida seed e engines também).

## API

| Método | Rota                        | Auth        | Observação |
|--------|-----------------------------|-------------|------------|
| GET    | `/api/health`               | —           | checa o banco (`SELECT 1`) |
| POST   | `/api/auth/login`           | —           | `{username,password}` → `{access_token,user}` |
| GET    | `/api/auth/me`              | Bearer      | perfil do token (inclui `balance`) |
| GET/POST | `/api/users`              | **admin**   | lista; cria com saldo inicial opcional |
| PATCH  | `/api/users/{id}`           | **admin**   | `{balance}` define o saldo final ou `{delta}` soma/desconta (não pode fechar negativo) |
| DELETE | `/api/users/{id}`           | **admin**   | apaga o jogador: cancela ordens abertas (banco+book), some estoque/saldo; trocas executadas ficam com `user_id=NULL`; guards: não apagar a si mesmo nem o último admin |
| GET    | `/api/commodities`          | —           | mercado aberto (`current_price`, `variation_24h`, `base_price`, `is_frozen`) |
| GET    | `/api/commodities/history`  | —           | `?limit=` ticks por commodity (alimenta os gráficos) |
| POST   | `/api/commodities`, `/seed`, `/refresh-prices` | **admin** | escrita |
| PATCH  | `/api/commodities/{id}`     | **admin**   | `{base_price}` troca a âncora nominal e recorta o book na nova faixa |
| POST   | `/api/commodities/{id}/shock` | **admin** | `{percent:-95..95}` choque: move todas as ordens abertas (recortado na faixa) e reprecifica na hora |
| POST   | `/api/commodities/{id}/freeze` | **admin** | `{frozen}` congela/reabre: congelada não aceita ordem nova (nem de bot) |
| POST   | `/api/commodities/{id}/clear-book` | **admin** | cancela todas as ordens abertas da commodity; `{reset_price:true}` devolve o preço ao nominal |
| POST   | `/api/commodities/reset`    | **admin**   | zerada geral: livro limpo + preços no nominal (histórico fica) |
| POST   | `/api/orders`               | Bearer      | cria ordem; **409** se congelada ou no limite de 10 abertas (`jogador_ordens_abertas_max`) |
| GET    | `/api/orders/mine`          | Bearer      | `{open, filled}` do usuário |
| DELETE | `/api/orders/{id}`          | Bearer      | cancela ordem aberta (dono; admin: qualquer uma). **404** inexistente/alheia, **409** já executada. Sem estorno |
| GET    | `/api/orders/book`          | —           | `?commodity_id=&depth=` livro de ofertas (topo do book em memória) |
| GET    | `/api/orders/open`, `/filled` | —         | `?commodity_id=&limit=` (limit 1..1000, padrão 200) |
| POST   | `/api/orders/prune`         | **admin**   | roda o prune na hora (TTL das abertas — bot 5 min / jogador 10 h — + histórico/ticks) |
| GET    | `/api/positions`            | Bearer      | carteira do jogador |
| GET/POST/PUT/DELETE | `/api/items`    | Bearer      | CRUD de exemplo |
| WS     | `/ws/market`                | —           | envia `init` e depois `market.tick`, `bot.activity`, `tax.applied` |

Docs interativos: `/docs` e `/openapi.json`.

## O que roda no boot (`lifespan` em `app/main.py`)

1. `init_db()` — cria as tabelas (`Base.metadata.create_all`) + migrações
   idempotentes: `ALTER TABLE users ADD COLUMN IF NOT EXISTS balance`,
   `ALTER TABLE commodities ADD COLUMN IF NOT EXISTS is_frozen` e
   `ALTER TABLE orders ADD COLUMN IF NOT EXISTS executed_quantity` (linhas
   legadas ficam com 0 — a quantidade original se perdeu quando a ordem zerou).
2. `UserController.ensure_admin()` — cria o admin do `.env` se não existir.
3. `CommodityController.seed_defaults()` — 5 commodities (Carvão, Aço, Trigo, Algodão, Café).
4. Saldo inicial do admin (`jogo_inicial_saldo`) se estiver 0.
5. `MarketEngine` + `BotEngine` em background, **compartilhando o mesmo `order_book`**
   (instância única exportada por `app/core/market/orderbook.py`).

Em shutdown, o `finally` cancela a task do engine.

## Cuidados ao editar (bugs que já quebraram isto)

- **`lifespan` precisa de `yield`.** Sem ele o `@asynccontextmanager` recebe uma
  corrotina comum e o app falha no startup com
  `TypeError: 'coroutine' object is not an async iterator`.
- **`SessionLocal` usa `expire_on_commit=False`** — é o que mantém os objetos ORM do
  order book utilizáveis depois do commit. Remover isso reintroduz
  `DetachedInstanceError` no sort/matching dos bots.
- **Session do SQLAlchemy não é segura entre threads.** Endpoints FastAPI rodam em
  threadpool; não compartilhe uma sessão entre request e engine. `OrderBook._persist`
  cria a própria sessão e atualiza por chave primária.
- **Nunca engula exceção sem log** em código de engine/loop (`except: rollback`
  silencioso escondeu por muito tempo a parada dos bots). Logue antes de continuar.
- **`app/models/__init__.py` deve exportar todos os models** — `init_db()` depende
  disso; se faltar, `create_all` não cria a tabela e o erro só aparece no primeiro insert.
- **O event bus é síncrono** (`events.py`). Handlers do WebSocket precisam agendar o
  envio com `asyncio.create_task(...)`; sempre `subscribe`/`unsubscribe` com o **mesmo**
  objeto de handler.
- **Preenchimento de ordens:** quando a quantidade zera, `OrderBook._match` marca
  `filled=True` e persiste. Qualquer dado com `quantity<=0 AND filled=false` quebra
  `GET /api/orders/open` (o controller também filtra por segurança).
  **`quantity` é o RESTANTE no book (zerada quando completa); o total já
  negociado é `executed_quantity`** (acumulado no `_match`, sempre `>= quantity`).
  O ticker de "Movimentações" e qualquer UI de "quanto trocou" leem
  `executed_quantity` — ler `quantity` em ordem preenchida mostra 0.
- Ordem criada pela API entra no banco **e** no `order_book` (senão nunca casa).
- Erros de negócio: lance as classes de `core/exceptions.py` — o handler global já
  devolve `{"detail": "..."}` com o status certo. Não devolva `HTTPException` solto.
- **Rotas literais antes das parametrizadas** no mesmo router (ex.:
  `POST /commodities/reset` antes de `PATCH /commodities/{id}`) — a ordem do
  FastAPI decide o match; invertendo, o literal vira 404/422.
- **Intervenções de admin**: mexa no banco e **depois** no `order_book`
  (`remove_ids`/`shock_prices`) — e sempre sob o lock do book quando for
  reprecificar (o matching roda no mesmo lock).

## Segurança / perfis

- `get_current_user` (login) e `get_current_admin` (perfil admin), ambos em `core/auth.py`.
- JWT: `sub` = id do usuário; algoritmo/segredo em `core/config.py`.
- CORS está com `allow_origins=["*"]` (ok pra dev; restringir em produção).
- A senha do admin só é aplicada **na criação** — para trocar depois, apague o
  usuário no banco e reinicie.

## Pendências conhecidas (decisões abertas, não "quebrado")

- `market.tick` publica `order_book.snapshot(0)` → sempre vazio; ainda não há
  snapshot por commodity no WebSocket (o frontend hoje faz polling: 4s mercado,
  2,5s book, 12s histórico — sem WS).
- `CommodityController.refresh_prices()` continua placeholder (`current_price =
  base_price + variation_24h`); quem calcula preço de verdade é
  `MarketEngine._update_commodity_prices()` → `preco_vivo()` (meio da melhor
  compra/venda + reversão ao nominal + corte na faixa).
- `_apply_sink_tax` sobe o `base_price` de todas as commodities (inflação) e
  publica `tax.applied`; ainda não debita saldo dos jogadores.
- Não há troca de senha nem DELETE de commodity (existe PATCH de commodity e
  DELETE/PATCH de usuário — ver API).
