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
# Install torch from PyTorch's CPU-only index BEFORE the project install so
# sentence-transformers picks up the CPU build instead of the default CUDA
# wheels. CUDA wheels pull in ~4GB of nvidia-* libraries we never use
# (SACP runs inference on CPU per spec 004 SC-001 "~80ms on CPU"); the bloat
# blew the GHCR push past the 5GB layer threshold and triggered "unknown blob"
# errors. The subsequent `pip install .` sees the torch requirement already
# satisfied and skips it.
RUN pip install --no-cache-dir --prefix=/install \
        --index-url https://download.pytorch.org/whl/cpu torch && \
    pip install --no-cache-dir --prefix=/install .

# ---- Runtime stage: slim base, no build tools ----
FROM python:3.14.4-slim-bookworm

WORKDIR /app

# Create unprivileged user before copying app files so chown applies cleanly.
# Numeric uid/gid (10001) is portable across hosts and avoids name lookups.
# --no-create-home: nothing in $HOME is needed at runtime.
RUN groupadd --system --gid 10001 sacp && \
    useradd --system --uid 10001 --gid sacp --no-create-home --shell /usr/sbin/nologin sacp

# Copy the installed site-packages + console scripts from the builder.
# /install/lib/python3.14/site-packages -> /usr/local/lib/python3.14/site-packages
# /install/bin/uvicorn etc. -> /usr/local/bin/
COPY --from=builder /install /usr/local

# Force a clean setuptools upgrade after the COPY. Two sources contribute
# vulnerable setuptools 70.2.0 (CVE-2025-47273): the runtime base image's
# bundled install AND pip's transitive resolution in the builder, which
# can land 70.x in /install. PR #158 stripped only the base image, missing
# the second source. --force-reinstall ensures the dist-info is regenerated
# cleanly so Trivy doesn't flag stale 70.x metadata sitting next to a 78+
# install. Capped <81 to keep pkg_resources available for transitive deps
# that may lazy-import it.
RUN pip install --no-cache-dir --upgrade --force-reinstall \
        'setuptools>=78.1.1,<81' && \
    rm -rf /root/.cache/pip

COPY --chown=sacp:sacp src/ src/
COPY --chown=sacp:sacp frontend/ frontend/
COPY --chown=sacp:sacp alembic/ alembic/
COPY --chown=sacp:sacp alembic/alembic.ini alembic.ini

# Drop root before exposing ports / running the app.
USER 10001:10001

EXPOSE 8750 8751

CMD ["sh", "-c", "alembic upgrade head && python -m src.run_apps"]
