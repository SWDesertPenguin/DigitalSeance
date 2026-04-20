"""FastAPI app factory for the SACP Web UI (port 8751).

This app is intentionally separate from the MCP server on 8750. It
shares the same database pool and service objects via the shared
lifespan so no duplicate resources are allocated, but its middleware
chain (strict CSP, own-origin CORS, no wildcard) is tailored for a
browser-facing surface.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

log = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_web_app() -> FastAPI:
    """Build and configure the Web UI FastAPI application."""
    app = FastAPI(
        title="SACP Web UI",
        version="0.1.0",
    )
    _add_healthcheck(app)
    _mount_static(app)
    return app


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


def _add_healthcheck(app: FastAPI) -> None:
    """Liveness endpoint that tests can hit without hitting the DB."""

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}
