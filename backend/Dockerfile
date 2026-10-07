# ---- etapa 1: dependências ----
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- etapa 2: imagem final ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

EXPOSE 3100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3100"]
