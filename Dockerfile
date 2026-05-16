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

# Copy uv from the official Astral distroless image (single-publisher,
# digest-stable). Pinning the uv minor here is deliberate — bumps land
# as their own PR so a compromised astral-sh maintainer can't quietly
# retag :latest. Closes the supply-chain class flagged by the LiteLLM
# 1.82.7-1.82.8 compromise: uv never lands via pip on the builder,
# which removes the entire pip-resolves-PyPI-fresh code path.
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /usr/local/bin/

# UV_LINK_MODE=copy: avoid hardlinks across mountpoints in the layered FS.
# UV_COMPILE_BYTECODE=1: precompile .pyc files in-place so first-request
#   latency on the running container isn't paying compile cost.
# UV_PYTHON_DOWNLOADS=never: refuse to download an interpreter; uv must
#   use the python:3.14.4-slim-bookworm one we picked above. Catches a
#   bad UV_PYTHON env override at build time.
# UV_NO_CACHE=1: don't write the global uv cache into the layer. The
#   sync below uses --no-cache too; the env var belts the same braces
#   for any sub-invocation (e.g. `uvx`).
# UV_PROJECT_ENVIRONMENT=/opt/sacp-venv: build the venv directly at the
#   runtime path. Console-script shebangs bake in the venv's python path
#   at install time; if the builder writes /build/.venv and the runtime
#   stage COPYs to /opt/sacp-venv, every script (alembic, uvicorn, ...)
#   carries a dangling `#!/build/.venv/bin/python` shebang and fails at
#   exec with "command not found". Building at the final path skips the
#   relocation problem entirely.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/sacp-venv

# Hash-verified install of every dep from uv.lock. `--frozen` refuses to
# re-resolve — if uv.lock is out of date vs pyproject.toml the build
# fails fast (CI gate `uv lock --check` catches this earlier). Every
# wheel hash in uv.lock is verified before install; a tampered wheel
# aborts the build, closing the supply-chain class flagged by the
# LiteLLM 1.82.7-1.82.8 compromise. `--no-install-project` skips the
# project itself (source ships via COPY into the runtime stage); `--no-dev`
# excludes the dev dependency group.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-dev --no-install-project

# Smoke-test the installed venv before promoting to the runtime stage.
# Catches resolver edge cases (missing markers, broken wheel installs,
# silent partial installs) at build time instead of at container start.
# Imports are restricted to packages declared in uv.lock — LiteLLM's
# per-provider SDKs (anthropic, etc.) are loaded lazily at dispatch time
# and aren't bundled.
RUN /opt/sacp-venv/bin/python -c "import litellm, fastapi, asyncpg, openai, mcp, sentence_transformers, torch, prometheus_client, jwt; print('smoke-test ok')"

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

# Copy the builder's venv (hash-verified install tree) into the same path
# it was built at. UV_PROJECT_ENVIRONMENT in the builder ensured every
# console-script shebang points here, so `alembic`, `uvicorn`, etc. work
# at exec time without a venv-relocation pass.
COPY --from=builder --chown=sacp:sacp /opt/sacp-venv /opt/sacp-venv
ENV PATH="/opt/sacp-venv/bin:$PATH" \
    VIRTUAL_ENV="/opt/sacp-venv"

COPY --chown=sacp:sacp src/ src/
COPY --chown=sacp:sacp frontend/ frontend/
COPY --chown=sacp:sacp alembic/ alembic/
COPY --chown=sacp:sacp alembic/alembic.ini alembic.ini

# sentence-transformers + huggingface_hub default their cache to ~/.cache,
# which resolves to /home/sacp under the unprivileged user — and that path
# doesn't exist (useradd --no-create-home above). First model load logs
# "Permission denied: '/home/sacp'" and the convergence engine fails open
# without embeddings, breaking spec 004 similarity scoring. Point HF_HOME
# at an app-owned cache dir the sacp user can write. Operators who want
# persistence across container restarts can mount a volume here in compose.
ENV HF_HOME=/app/.cache/huggingface
RUN mkdir -p /app/.cache/huggingface && chown -R sacp:sacp /app/.cache

# Drop root before exposing ports / running the app.
USER 10001:10001

EXPOSE 8750 8751

# Liveness probe via the web-UI /healthz endpoint (no DB touch). Compose
# overrides this when running under docker-compose; this instruction
# covers anyone running the image directly. Python stdlib only — slim
# image has no curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8751/healthz', timeout=3).status == 200 else 1)" || exit 1

CMD ["sh", "-c", "alembic upgrade head && python -m src.run_apps"]
