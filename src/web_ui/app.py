"""FastAPI app factory for the SACP Web UI (port 8751).

Separate from the MCP server on 8750 so it can run a stricter security
posture (no wildcard CORS, tight CSP, HttpOnly cookies). Shares the
same database pool and service objects as the MCP app via
``src/web_ui/shared.py``.

Lifespan behavior:
  - If the app is launched via ``src/run_apps.py`` in the same process
    as the MCP server, ``prime_from_mcp_app`` attaches shared services
    BEFORE uvicorn starts serving.
  - Standalone (e.g. ``uvicorn src.web_ui.app:create_web_app --factory``)
    the lifespan provisions its own pool + services.
  - Under pytest TestClient with no injected services the lifespan
    silently skips DB setup so `/healthz` and static-file tests work
    without a database.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.web_ui.auth import router as auth_router
from src.web_ui.security import add_csrf_header_check, add_security_headers, add_strict_cors
from src.web_ui.shared import (
    SharedServices,
    attach_to_app,
    build_standalone_services,
    close_standalone_services,
)

log = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Provision services if the caller hasn't already.

    Tests + run_apps set ``app.state.pool`` prior to startup; when that
    attribute is missing we attempt to build a standalone pool. Failures
    are logged and the app keeps running so non-DB routes (healthz,
    static files) still work.
    """
    owned: SharedServices | None = None
    if not hasattr(app.state, "pool"):
        try:
            owned = await build_standalone_services()
            attach_to_app(app, owned)
        except Exception:  # noqa: BLE001 — keep tests that don't need DB working
            log.warning("Web UI lifespan: standalone services unavailable", exc_info=True)
    yield
    if owned is not None:
        await close_standalone_services(owned)


def create_web_app() -> FastAPI:
    """Build and configure the Web UI FastAPI application."""
    app = FastAPI(title="SACP Web UI", version="0.1.0", lifespan=_lifespan)
    add_security_headers(app)
    add_csrf_header_check(app)
    add_strict_cors(app)
    _add_healthcheck(app)
    app.include_router(auth_router)
    _mount_static(app)
    return app


def _add_healthcheck(app: FastAPI) -> None:
    """Liveness endpoint that tests can hit without hitting the DB."""

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}


def _mount_static(app: FastAPI) -> None:
    """Serve the frontend/ directory as static files at root."""
    if not _FRONTEND_DIR.exists():
        log.warning("frontend/ directory missing at %s", _FRONTEND_DIR)
        return
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIR), html=True),
        name="frontend",
    )
