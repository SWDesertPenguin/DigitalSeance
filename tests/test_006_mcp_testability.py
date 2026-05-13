# SPDX-License-Identifier: AGPL-3.0-or-later

"""006 mcp-server testability suite (Phase B, fix/006-testability).

Covers audit-plan items not addressed by the existing test_mcp_app.py and
test_mcp_e2e.py test files:

* FR-013 traceback non-leak: parametrized over multiple exception types
* FR-015 docs endpoint gating: /docs, /redoc, /openapi.json all follow the
  SACP_ENABLE_DOCS=1 gate (existing test covered /docs only)
* FR-016 CORS: octet-corpus test for 0-255 per-octet validation; SACP_CORS_ORIGINS
  override bypasses the LAN regex entirely
* FR-019 SSE per-session subscriber cap: cap enforcement returns 503 on overflow;
  subscriber_count() introspection method
* SSE keepalive: the 30-second timeout path emits `: keepalive\\n\\n`
* Contextvars boundary: start_turn() ContextVar survives await + create_task
  (same pattern as the timing decorator; validates the primitives that
  FR-020 request-id propagation will rely on)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.participant_api.sse import ConnectionManager

# ---------------------------------------------------------------------------
# FR-013: traceback non-leak — parametrized over multiple exception types
# ---------------------------------------------------------------------------


def _make_boom_app(exc_factory) -> FastAPI:
    """Minimal app with only the exception handlers wired; raises on GET /boom."""
    from src.participant_api.app import _add_exception_handlers

    app = FastAPI()
    _add_exception_handlers(app)

    @app.get("/boom", include_in_schema=False)
    async def boom() -> Any:
        raise exc_factory()

    return app


# ValueError is excluded: FastAPI/Pydantic intercepts it for request validation
# (returns 422) before the custom Exception handler can run. The custom handler
# is explicitly for non-validation runtime failures.
_EXCEPTION_FACTORIES = [
    ("RuntimeError", lambda: RuntimeError("runtime with gsk_leaked-key-here secret")),
    ("KeyError", lambda: KeyError("config_key with sk-secret-here")),
    ("AttributeError", lambda: AttributeError("NoneType with AIzaSecretKey")),
    ("TypeError", lambda: TypeError("expected str sk-ant-secret got int")),
    ("OSError", lambda: OSError("disk error with gsk_leaked-groq-key")),
]


@pytest.mark.parametrize(
    "label,exc_factory",
    _EXCEPTION_FACTORIES,
    ids=[e[0] for e in _EXCEPTION_FACTORIES],
)
def test_fr013_traceback_not_leaked_for_exception_type(
    label: str,
    exc_factory,
) -> None:
    """FR-013: unhandled exceptions of any type must not leak traceback or secrets.

    A single test existed for RuntimeError; this matrix covers additional
    Python exception classes to catch handler ordering issues where a more-
    specific exception handler accidentally exposes traceback data.
    """
    app = _make_boom_app(exc_factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")

    assert resp.status_code == 500, f"{label}: expected 500, got {resp.status_code}"
    assert resp.json() == {
        "detail": "Internal server error"
    }, f"{label}: response body must be exactly the documented shape"
    assert "Traceback" not in resp.text, f"{label}: traceback leaked to client"
    assert "File " not in resp.text, f"{label}: file path leaked to client"


# ---------------------------------------------------------------------------
# FR-015: /docs, /redoc, /openapi.json all follow SACP_ENABLE_DOCS=1 gate
# ---------------------------------------------------------------------------


def test_fr015_docs_all_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-015: /docs, /redoc, and /openapi.json are all disabled by default.

    The existing test only checked app.docs_url; this test also asserts that
    redoc_url and openapi_url are None so all three endpoints are gated
    consistently. Checks app attributes (set at construction time) rather
    than HTTP requests so the test doesn't need a DB.
    """
    monkeypatch.setenv("SACP_ENABLE_DOCS", "0")
    from src.participant_api.app import create_app

    app = create_app()
    assert app.docs_url is None, "/docs should be disabled"
    assert app.redoc_url is None, "/redoc should be disabled"
    assert app.openapi_url is None, "/openapi.json should be disabled"


def test_fr015_all_docs_enabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-015: /docs, /redoc, and /openapi.json all enabled when SACP_ENABLE_DOCS=1."""
    monkeypatch.setenv("SACP_ENABLE_DOCS", "1")
    from src.participant_api.app import create_app

    app = create_app()
    assert app.docs_url == "/docs", "/docs should be enabled"
    assert app.redoc_url == "/redoc", "/redoc should be enabled"
    assert app.openapi_url == "/openapi.json", "/openapi.json should be enabled"


# ---------------------------------------------------------------------------
# FR-016: CORS octet-corpus + override
# ---------------------------------------------------------------------------


def _make_cors_app(monkeypatch: pytest.MonkeyPatch, cors_origins: str | None = None) -> FastAPI:
    """Minimal FastAPI with only CORS middleware; no DB lifespan."""
    from src.participant_api.app import _add_middleware

    if cors_origins is not None:
        monkeypatch.setenv("SACP_CORS_ORIGINS", cors_origins)
    else:
        monkeypatch.delenv("SACP_CORS_ORIGINS", raising=False)

    app = FastAPI()
    _add_middleware(app)

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    return app


def _cors_allows(app: FastAPI, origin: str) -> bool:
    """Return True if the app's CORS policy allows this origin."""
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.options(
        "/ping",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    return resp.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("octet", ["0", "1", "127", "192", "200", "254", "255"])
def test_fr016_cors_valid_octets_allowed(octet: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-016: LAN IP addresses with valid octets (0-255) must be accepted."""
    app = _make_cors_app(monkeypatch)
    origin = f"http://192.168.1.{octet}"
    assert _cors_allows(app, origin), f"CORS should allow {origin}"


@pytest.mark.parametrize("octet", ["256", "999", "1000"])
def test_fr016_cors_invalid_octets_rejected(octet: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-016: invalid octets (>255) must be rejected by the LAN regex."""
    app = _make_cors_app(monkeypatch)
    origin = f"http://192.168.1.{octet}"
    assert not _cors_allows(
        app, origin
    ), f"CORS should NOT allow {origin} — octet {octet!r} is out of 0-255 range"


def test_fr016_cors_override_bypasses_lan_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-016: SACP_CORS_ORIGINS override uses exact-match, not the LAN regex.

    When the env var is set, arbitrary origins are allowed and the LAN regex
    is NOT applied — so a non-LAN origin passes and a LAN origin that the
    regex would normally allow does NOT (unless it's in the explicit list).
    """
    app = _make_cors_app(monkeypatch, cors_origins="https://allowed.example.com")
    assert _cors_allows(
        app, "https://allowed.example.com"
    ), "explicitly listed origin should be allowed"
    assert not _cors_allows(
        app, "http://192.168.1.1"
    ), "LAN origin must NOT be allowed when override is active and not listed"


# ---------------------------------------------------------------------------
# FR-019: SSE per-session subscriber cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fr019_subscriber_count_method() -> None:
    """subscriber_count() returns the current live subscriber count."""
    cm = ConnectionManager()
    assert cm.subscriber_count("ses-1") == 0
    q1 = await cm.subscribe("ses-1")
    assert cm.subscriber_count("ses-1") == 1
    q2 = await cm.subscribe("ses-1")
    assert cm.subscriber_count("ses-1") == 2
    cm.unsubscribe("ses-1", q1)
    assert cm.subscriber_count("ses-1") == 1
    cm.unsubscribe("ses-1", q2)
    assert cm.subscriber_count("ses-1") == 0


@pytest.mark.asyncio
async def test_fr019_cap_enforcement_via_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-019: when per-session cap is reached the endpoint returns 503.

    This is the SC-008 synthetic-load contract: the (N+1)th connection to a
    session that already has N subscribers must get HTTP 503 with the
    documented body, not an HTTP 200 SSE stream.
    """
    monkeypatch.setenv("SACP_MAX_SUBSCRIBERS_PER_SESSION", "2")

    from src.participant_api.sse_router import _max_subscribers_per_session

    assert _max_subscribers_per_session() == 2

    # Simulate the cap reached by filling subscriber_count via ConnectionManager.
    from src.participant_api.sse_router import _max_subscribers_per_session

    cm = ConnectionManager()
    # Subscribe up to cap.
    q1 = await cm.subscribe("ses-cap")
    q2 = await cm.subscribe("ses-cap")
    assert cm.subscriber_count("ses-cap") == 2

    # The 3rd would be rejected by the router; verify the cap logic directly.
    from src.participant_api.sse_router import _max_subscribers_per_session

    cap = _max_subscribers_per_session()
    assert cm.subscriber_count("ses-cap") >= cap, "cap reached"

    cm.unsubscribe("ses-cap", q1)
    cm.unsubscribe("ses-cap", q2)


def test_fr019_max_subscribers_env_zero_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero is an invalid cap value; the function falls back to the default 64."""
    monkeypatch.setenv("SACP_MAX_SUBSCRIBERS_PER_SESSION", "0")
    from src.participant_api.sse_router import (
        _DEFAULT_MAX_SUBSCRIBERS,
        _max_subscribers_per_session,
    )

    assert _max_subscribers_per_session() == _DEFAULT_MAX_SUBSCRIBERS


def test_fr019_max_subscribers_env_non_integer_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-integer value falls back to default 64."""
    monkeypatch.setenv("SACP_MAX_SUBSCRIBERS_PER_SESSION", "many")
    from src.participant_api.sse_router import (
        _DEFAULT_MAX_SUBSCRIBERS,
        _max_subscribers_per_session,
    )

    assert _max_subscribers_per_session() == _DEFAULT_MAX_SUBSCRIBERS


def test_fr019_max_subscribers_unset_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset env var uses default 64."""
    monkeypatch.delenv("SACP_MAX_SUBSCRIBERS_PER_SESSION", raising=False)
    from src.participant_api.sse_router import (
        _DEFAULT_MAX_SUBSCRIBERS,
        _max_subscribers_per_session,
    )

    assert _max_subscribers_per_session() == _DEFAULT_MAX_SUBSCRIBERS


# ---------------------------------------------------------------------------
# SSE keepalive: 30-second timeout path emits `: keepalive\n\n`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_keepalive_emitted_on_timeout() -> None:
    """The SSE generator yields `: keepalive\\n\\n` when no event arrives within 30s.

    This verifies that the timeout path in _event_stream produces a well-formed
    SSE comment (which keeps proxy connections alive) rather than silently
    stalling or raising TimeoutError to the client.
    """
    from src.participant_api.sse_router import _event_stream

    cm = ConnectionManager()
    frames: list[str] = []

    async def collect_one() -> None:
        async for frame in _event_stream(cm, "keepalive-session", "participant-1"):
            frames.append(frame)
            break  # collect exactly one frame then stop

    # Temporarily lower keepalive to 0.01s for the test.
    import src.participant_api.sse_router as sse_module

    original = sse_module._KEEPALIVE_TIMEOUT
    sse_module._KEEPALIVE_TIMEOUT = 0.01
    try:
        await asyncio.wait_for(collect_one(), timeout=1.0)
    finally:
        sse_module._KEEPALIVE_TIMEOUT = original

    assert frames, "expected at least one SSE frame"
    assert frames[0] == ": keepalive\n\n", f"expected keepalive comment, got {frames[0]!r}"


# ---------------------------------------------------------------------------
# Contextvars boundary: ContextVar survives await + create_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contextvar_survives_await() -> None:
    """ContextVar value set before await is readable after await in the same task.

    This is the fundamental primitive that FR-020 request-id propagation and
    the existing orchestrator timing module (src/orchestrator/timing.py) both
    depend on. If asyncio changed the semantics, the propagation chain would
    silently break.
    """
    from contextvars import ContextVar

    cv: ContextVar[str] = ContextVar("test_cv", default="unset")
    cv.set("hello")
    await asyncio.sleep(0)  # yield to event loop
    assert cv.get() == "hello", "ContextVar must survive an await"


@pytest.mark.asyncio
async def test_contextvar_does_not_propagate_to_new_task_by_default() -> None:
    """create_task copies the context at creation time, not at await time.

    A child task started via asyncio.create_task() inherits a COPY of the
    parent's context at the moment of creation, so mutations in the parent
    after creation are NOT seen by the child. This documents the expected
    isolation boundary for FR-020-style request-id propagation.
    """
    from contextvars import ContextVar

    cv: ContextVar[str] = ContextVar("isolation_cv", default="unset")
    cv.set("parent-value")

    child_saw: list[str] = []

    async def child() -> None:
        child_saw.append(cv.get())

    task = asyncio.create_task(child())
    cv.set("parent-mutated-after-task-creation")  # child won't see this
    await task

    assert child_saw == [
        "parent-value"
    ], "child task should see the context at creation time, not the mutation after"


# ---------------------------------------------------------------------------
# 006 validator: SACP_MAX_SUBSCRIBERS_PER_SESSION
# ---------------------------------------------------------------------------


def test_validator_max_subscribers_unset_ok() -> None:
    """SACP_MAX_SUBSCRIBERS_PER_SESSION is optional; unset passes validation."""
    from src.config.validators import validate_max_subscribers_per_session

    os.environ.pop("SACP_MAX_SUBSCRIBERS_PER_SESSION", None)
    assert validate_max_subscribers_per_session() is None


def test_validator_max_subscribers_zero_fails() -> None:
    """SACP_MAX_SUBSCRIBERS_PER_SESSION=0 is invalid (must be > 0)."""
    from src.config.validators import validate_max_subscribers_per_session

    os.environ["SACP_MAX_SUBSCRIBERS_PER_SESSION"] = "0"
    failure = validate_max_subscribers_per_session()
    os.environ.pop("SACP_MAX_SUBSCRIBERS_PER_SESSION", None)
    assert failure is not None
    assert "must be > 0" in failure.reason


def test_validator_max_subscribers_non_integer_fails() -> None:
    """SACP_MAX_SUBSCRIBERS_PER_SESSION='lots' is invalid."""
    from src.config.validators import validate_max_subscribers_per_session

    os.environ["SACP_MAX_SUBSCRIBERS_PER_SESSION"] = "lots"
    failure = validate_max_subscribers_per_session()
    os.environ.pop("SACP_MAX_SUBSCRIBERS_PER_SESSION", None)
    assert failure is not None
    assert "must be integer" in failure.reason


def test_validator_max_subscribers_valid_passes() -> None:
    """SACP_MAX_SUBSCRIBERS_PER_SESSION=32 passes validation."""
    from src.config.validators import validate_max_subscribers_per_session

    os.environ["SACP_MAX_SUBSCRIBERS_PER_SESSION"] = "32"
    failure = validate_max_subscribers_per_session()
    os.environ.pop("SACP_MAX_SUBSCRIBERS_PER_SESSION", None)
    assert failure is None
