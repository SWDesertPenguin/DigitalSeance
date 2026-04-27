# ---- Builder stage: install deps with build toolchain available ----
# Pinned to a specific Python minor + Debian release. Bookworm = Debian 12,
# glibc — keeps wheels (torch, numpy, sentence-transformers) ABI-compatible
# without forcing source builds. Bump quarterly when Python patches release.
FROM python:3.14.4-slim-bookworm AS builder

WORKDIR /build

# gcc + libpq-dev are kept here in case any wheel falls back to source.
# They never ship in the final image.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# ---- Runtime stage: slim base, no build tools ----
FROM python:3.14.4-slim-bookworm

WORKDIR /app

# Copy the installed site-packages + console scripts from the builder.
# /install/lib/python3.14/site-packages -> /usr/local/lib/python3.14/site-packages
# /install/bin/uvicorn etc. -> /usr/local/bin/
COPY --from=builder /install /usr/local

COPY src/ src/
COPY frontend/ frontend/
COPY alembic/ alembic/
COPY alembic/alembic.ini alembic.ini

EXPOSE 8750 8751

CMD ["sh", "-c", "alembic upgrade head && python -m src.run_apps"]
