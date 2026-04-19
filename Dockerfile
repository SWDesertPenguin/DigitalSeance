# ---- Builder stage: install deps with build toolchain available ----
FROM python:3.11-slim AS builder

WORKDIR /build

# gcc + libpq-dev are kept here in case any wheel falls back to source.
# They never ship in the final image.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# ---- Runtime stage: slim base, no build tools ----
FROM python:3.11-slim

WORKDIR /app

# Copy the installed site-packages + console scripts from the builder.
# /install/lib/python3.11/site-packages -> /usr/local/lib/python3.11/site-packages
# /install/bin/uvicorn etc. -> /usr/local/bin/
COPY --from=builder /install /usr/local

COPY src/ src/
COPY alembic/ alembic/
COPY alembic/alembic.ini alembic.ini

EXPOSE 8750

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.mcp_server.app:create_app --host 0.0.0.0 --port 8750 --factory"]
