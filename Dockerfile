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

# Bootstrap uv only to expand uv.lock into a hash-pinned requirements file.
# uv does not ship in the runtime image — pip is the actual installer.
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

# Install torch from PyTorch's CPU-only index BEFORE the locked deps so
# sentence-transformers picks up the CPU build instead of the default CUDA
# wheels. CUDA wheels pull in ~4GB of nvidia-* libraries we never use
# (SACP runs inference on CPU per spec 004 SC-001 "~80ms on CPU"); the bloat
# blew the GHCR push past the 5GB layer threshold and triggered "unknown blob"
# errors. PyTorch's CPU index is single-publisher (the PyTorch project
# itself), so skipping --require-hashes here is a narrower trust posture
# than the multi-publisher PyPI risk model the next step closes off.
RUN pip install --no-cache-dir --prefix=/install \
        --index-url https://download.pytorch.org/whl/cpu torch

# Make the previously-installed torch visible to subsequent pip invocations
# so they don't try to re-resolve torch from PyPI (which would land the
# 4GB CUDA build and bust the GHCR layer cap).
ENV PYTHONPATH=/install/lib/python3.14/site-packages

# Generate a hash-pinned requirements file from uv.lock, excluding torch
# (handled above) plus the GPU stack (nvidia-*, cuda-*, triton) that
# uv.lock pins as torch transitive deps even though our torch wheel is
# CPU-only. Leaving them in adds ~3.5 GB to the image and pushed the
# GHCR upload past its EOF threshold. The exported file lists every
# remaining transitive dependency with the exact wheel hash recorded in
# uv.lock; --require-hashes refuses to install any wheel whose content
# doesn't match, closing the supply-chain class flagged by the LiteLLM
# 1.82.7-1.82.8 compromise.
RUN uv export \
        --no-dev \
        --no-emit-project \
        --format requirements-txt \
        --output-file /tmp/requirements-all.txt && \
    awk '/^[a-zA-Z]/ { \
            name = $1; sub(/==.*/, "", name); \
            skip = (name == "torch" || name == "triton" || \
                    name ~ /^nvidia-/ || name ~ /^cuda-/) ? 1 : 0 \
         } !skip' \
        /tmp/requirements-all.txt > /tmp/requirements.txt

# Hash-verified install of every other dep from uv.lock. Without the
# --require-hashes flag, pip resolves PyPI fresh on every build and
# accepts any wheel claiming the right version — the LiteLLM compromise
# vector. With it, a tampered wheel fails install and the build aborts.
RUN pip install --no-cache-dir --prefix=/install \
        --require-hashes -r /tmp/requirements.txt

# ---- Runtime stage: slim base, no build tools ----
FROM python:3.14.4-slim-bookworm

WORKDIR /app

# Apply Debian bookworm point-release updates published since the upstream
# base image was last rebuilt. The python:slim image rebuilds on its own
# cadence; running upgrade here narrows the window between the base rebuild
# and our build, picking up any security fixes Debian has shipped in the
# meantime. Placed before user creation and the COPY layers so it caches
# independently of app code churn.
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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
