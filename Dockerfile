# Repo root = build context (admin, display, server, tel 모두 포함)
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY admin ./admin
COPY display ./display
COPY tel ./tel

WORKDIR /app/server

ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
