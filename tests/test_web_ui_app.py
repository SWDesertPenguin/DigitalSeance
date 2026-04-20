"""Smoke tests for the Phase 2 Web UI FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.web_ui.app import create_web_app


def test_create_web_app_returns_fastapi() -> None:
    """Factory returns a working app instance."""
    app = create_web_app()
    assert app.title == "SACP Web UI"


def test_healthcheck_returns_ok() -> None:
    """/healthz returns {'status': 'ok'} so container healthchecks can rely on it."""
    app = create_web_app()
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_mounted_at_root() -> None:
    """The frontend/ directory is served as static files; index.html is the fall-through."""
    app = create_web_app()
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "SACP Web UI" in response.text
