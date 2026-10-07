# Simulação Econômica

Estrutura básica **FastAPI + React PWA + PostgreSQL**, tudo em Docker Compose.

```
.
├── docker-compose.yml
├── .env.example
├── backend/          # FastAPI (porta 3100)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # app FastAPI + middlewares + routers + seed do admin
│       ├── core/              # config, database, exceptions, error handlers, security, auth
│       ├── routers/           # camada HTTP (health, auth, users, items)
│       ├── controllers/       # regras de negócio
│       ├── models/            # models ORM (SQLAlchemy)
│       └── schemas/           # DTOs (Pydantic)
└── frontend/         # React + Vite + PWA (porta 3200)
    ├── Dockerfile
    ├── nginx.conf             # serve o build e faz proxy de /api -> backend
    ├── public/                # manifest.webmanifest, sw.js, icon.svg
    └── src/                   # App.jsx, api.js, components/ (Login, Users), styles.css
```

## Portas

| Serviço  | Porta  |
|----------|--------|
| Frontend | 3200   |
| Backend  | 3100   |
| Postgres | 5432   |

## Autenticação

- **Tabela `users`** criada automaticamente no boot (`init_db`).
- **Admin padrão** criado no primeiro start a partir do `.env`:
  `ADMIN_USERNAME` / `ADMIN_PASSWORD` (padrão: `admin` / `admin`).
- **Login:** `POST /api/auth/login` → devolve `{ access_token, user }` (JWT Bearer,
  expira em `JWT_EXPIRE_MINUTES`, padrão 12h).
- **Rota protegida:** envie `Authorization: Bearer <token>` — todos os `/api/items`
  exigem login; `/api/users` (listar/criar) exige perfil admin.
- **Somente o admin cria usuários:** `POST /api/users` retorna 403 para não-admin.
- No frontend, sem sessão exibe a tela de **Login**; o token fica no
  `localStorage` e a sessão expirada força o logout automático.

Exemplo:

```bash
TOKEN=$(curl -s -X POST http://localhost:3100/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://localhost:3100/api/users
curl -X POST http://localhost:3100/api/users \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"username":"maria","password":"1234","is_admin":false}'
```

> Troque `ADMIN_PASSWORD` e `JWT_SECRET` no `.env` antes de usar em produção.
> Observação: a senha do admin só é aplicada na criação — para alterá-la depois,
> apague o usuário no banco e reinicie o backend.

## Subindo tudo

```bash
docker compose up --build -d
```

- Front: http://localhost:3200
- API + docs: http://localhost:3100/docs
- Health: http://localhost:3100/api/health

## Desenvolvimento local (sem Docker)

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 3100
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # sobe na 3200 e faz proxy de /api para :3100
```

## Camadas do backend

`router (HTTP) -> controller (regra) -> model/schema (dados)`

Para criar um novo recurso:

1. `app/models/<recurso>.py` — model SQLAlchemy
2. `app/schemas/<recurso>.py` — schemas Pydantic
3. `app/controllers/<recurso>_controller.py` — regras de negócio
4. `app/routers/<recurso>_router.py` — rotas
5. Registrar o router em `app/main.py`
