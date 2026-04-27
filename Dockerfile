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

# Create unprivileged user before copying app files so chown applies cleanly.
# Numeric uid/gid (10001) is portable across hosts and avoids name lookups.
# --no-create-home: nothing in $HOME is needed at runtime.
RUN groupadd --system --gid 10001 sacp && \
    useradd --system --uid 10001 --gid sacp --no-create-home --shell /usr/sbin/nologin sacp

# Copy the installed site-packages + console scripts from the builder.
# /install/lib/python3.11/site-packages -> /usr/local/lib/python3.11/site-packages
# /install/bin/uvicorn etc. -> /usr/local/bin/
COPY --from=builder /install /usr/local

COPY --chown=sacp:sacp src/ src/
COPY --chown=sacp:sacp frontend/ frontend/
COPY --chown=sacp:sacp alembic/ alembic/
COPY --chown=sacp:sacp alembic/alembic.ini alembic.ini

# Drop root before exposing ports / running the app.
USER 10001:10001

EXPOSE 8750 8751

CMD ["sh", "-c", "alembic upgrade head && python -m src.run_apps"]
