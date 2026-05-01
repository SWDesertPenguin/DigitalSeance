"""MCP app tests — application creation and router registration."""

from __future__ import annotations

import asyncio

from src.mcp_server.app import create_app
from src.mcp_server.sse import ConnectionManager


def test_create_app_returns_fastapi() -> None:
    """create_app returns a FastAPI instance."""
    app = create_app()
    assert app.title == "SACP MCP Server"


def test_app_has_routers() -> None:
    """App includes participant, facilitator, and session routers."""
    app = create_app()
    paths = [r.path for r in app.routes]
    has_participant = any("/tools/participant" in p for p in paths)
    has_facilitator = any("/tools/facilitator" in p for p in paths)
    has_session = any("/tools/session" in p for p in paths)
    assert has_participant
    assert has_facilitator
    assert has_session


def test_app_has_cors() -> None:
    """App has CORS middleware configured."""
    app = create_app()
    assert len(app.user_middleware) > 0


def test_docs_disabled_by_default() -> None:
    """OpenAPI / Swagger UI is off unless SACP_ENABLE_DOCS=1 (006 CHK014)."""
    app = create_app()
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_docs_enabled_via_env(monkeypatch) -> None:
    """SACP_ENABLE_DOCS=1 turns the Swagger UI back on for dev / on-host use."""
    monkeypatch.setenv("SACP_ENABLE_DOCS", "1")
    app = create_app()
    assert app.docs_url == "/docs"


def test_unhandled_exception_returns_generic_500() -> None:
    """Global Exception handler hides the traceback (006 CHK010)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.mcp_server.app import _add_exception_handlers

    app = FastAPI()
    _add_exception_handlers(app)

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("secret traceback content sk-leaked-key-12345abcdef")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body == {"detail": "Internal server error"}
    assert "secret traceback content" not in resp.text
    assert "sk-leaked-key" not in resp.text


async def test_sse_queue_overflow_drops_event() -> None:
    """A wedged consumer with a full queue gets dropped, broadcast continues (006 CHK029)."""
    cm = ConnectionManager(queue_maxsize=2)
    q = await cm.subscribe("session-1")
    await cm.broadcast("session-1", {"n": 1})
    await cm.broadcast("session-1", {"n": 2})
    # Queue is now at maxsize; this third broadcast should drop, not block
    await asyncio.wait_for(cm.broadcast("session-1", {"n": 3}), timeout=0.5)
    assert q.qsize() == 2


async def test_sse_unsubscribe_clears_session() -> None:
    """unsubscribe drops the queue and prunes empty session entries."""
    cm = ConnectionManager()
    q = await cm.subscribe("session-1")
    cm.unsubscribe("session-1", q)
    assert "session-1" not in cm._queues


def test_sensitive_fields_cover_obvious_patterns() -> None:
    """CI guard for 010 CHK001: any Participant field whose name matches a
    known-sensitive heuristic (`_encrypted`, `_hash`, `_lookup`, or `bound_ip`)
    MUST be in the debug-export strip-list. Catches the case where a
    developer adds a new sensitive column without remembering to update
    _SENSITIVE_FIELDS. The `_lookup` suffix covers HMAC token-lookup style
    columns added under audit C-02.
    """
    from dataclasses import fields

    from src.mcp_server.tools.debug import _SENSITIVE_FIELDS
    from src.models.participant import Participant

    suspicious = {
        f.name
        for f in fields(Participant)
        if f.name.endswith(("_encrypted", "_hash", "_lookup")) or f.name == "bound_ip"
    }
    missing = suspicious - _SENSITIVE_FIELDS
    assert not missing, (
        f"Sensitive-looking Participant fields not in debug.py _SENSITIVE_FIELDS: "
        f"{sorted(missing)}. Add them so the debug export strips them."
    )


def test_config_snapshot_drops_secret_name_pattern(monkeypatch) -> None:
    """010 CHK005: secret-named env vars are filtered out of the snapshot
    even if they sneak into the allowlist.
    """
    from src.mcp_server.tools import debug

    monkeypatch.setattr(
        debug,
        "_CONFIG_KEYS",
        ("SACP_CONTEXT_MAX_TURNS", "SACP_DB_PASSWORD", "SACP_FAKE_SECRET"),
    )
    monkeypatch.setenv("SACP_CONTEXT_MAX_TURNS", "20")
    monkeypatch.setenv("SACP_DB_PASSWORD", "hunter2")
    monkeypatch.setenv("SACP_FAKE_SECRET", "sk-leaked-key-12345abcdef")
    snap = debug._config_snapshot()
    assert "SACP_CONTEXT_MAX_TURNS" in snap
    assert "SACP_DB_PASSWORD" not in snap
    assert "SACP_FAKE_SECRET" not in snap
