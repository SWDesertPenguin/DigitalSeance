# SPDX-License-Identifier: AGPL-3.0-or-later

"""MCP auth middleware tests — token validation and rejection."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_test_app() -> object:
    """Create a minimal test app with auth middleware."""
    from fastapi import Depends, FastAPI

    from src.mcp_server.middleware import get_current_participant

    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(
        participant: object = Depends(get_current_participant),
    ) -> dict:
        return {"id": participant.id}

    return app


def test_missing_token_returns_403() -> None:
    """Request without Authorization header returns 403."""
    app = _make_test_app()
    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code in (401, 403)


def test_invalid_bearer_format_returns_403() -> None:
    """Malformed Authorization header returns 403."""
    app = _make_test_app()
    client = TestClient(app)
    response = client.get(
        "/test",
        headers={"Authorization": "NotBearer token"},
    )
    assert response.status_code in (401, 403)
