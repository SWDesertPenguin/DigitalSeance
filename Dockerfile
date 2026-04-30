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

# Explicitly remove every setuptools-related directory after the COPY,
# THEN install a clean fixed version. Two sources contribute vulnerable
# setuptools 70.2.0 (CVE-2025-47273): the runtime base image AND pip's
# transitive resolution in the builder. After the COPY both have landed
# their own setuptools-*.dist-info dirs side-by-side in site-packages.
# PR #158 (pre-COPY rm) handled only the base. PR #160 (post-COPY pip
# --force-reinstall) cleaned only one of the two duplicate dist-info
# dirs because pip's uninstaller can't reliably handle two installed
# copies of the same package — it finds one via importlib.metadata and
# leaves the other as orphan metadata. Wipe the slate first, then
# install fresh: only one dist-info dir exists when pip is done.
# Capped <81 to keep pkg_resources available for transitive deps that
# may lazy-import it.
RUN rm -rf /usr/local/lib/python3.14/site-packages/setuptools \
           /usr/local/lib/python3.14/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.14/site-packages/pkg_resources \
           /usr/local/lib/python3.14/site-packages/_distutils_hack && \
    pip install --no-cache-dir 'setuptools>=78.1.1,<81' && \
    rm -rf /root/.cache/pip

COPY --chown=sacp:sacp src/ src/
COPY --chown=sacp:sacp frontend/ frontend/
COPY --chown=sacp:sacp alembic/ alembic/
COPY --chown=sacp:sacp alembic/alembic.ini alembic.ini

# Drop root before exposing ports / running the app.
USER 10001:10001

EXPOSE 8750 8751

CMD ["sh", "-c", "alembic upgrade head && python -m src.run_apps"]
