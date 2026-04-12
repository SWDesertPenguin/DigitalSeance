FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY src/ src/
COPY alembic/ alembic/
COPY alembic/alembic.ini alembic.ini

EXPOSE 8750

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.mcp_server.app:create_app --host 0.0.0.0 --port 8750 --factory"]
