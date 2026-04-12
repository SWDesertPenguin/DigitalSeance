"""MCP app tests — application creation and router registration."""

from __future__ import annotations

from src.mcp_server.app import create_app


def test_create_app_returns_fastapi() -> None:
    """create_app returns a FastAPI instance."""
    app = create_app()
    assert app.title == "SACP MCP Server"


def test_app_has_routers() -> None:
    """App includes participant, facilitator, and session routers."""
    app = create_app()
    paths = [r.path for r in app.routes]
    # Check that tool prefixes are registered
    has_participant = any("/tools/participant" in p for p in paths)
    has_facilitator = any("/tools/facilitator" in p for p in paths)
    has_session = any("/tools/session" in p for p in paths)
    assert has_participant
    assert has_facilitator
    assert has_session


def test_app_has_cors() -> None:
    """App has CORS middleware configured."""
    app = create_app()
    # CORS is added via add_middleware
    assert len(app.user_middleware) > 0
