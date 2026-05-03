"""Same-origin MCP proxy tests (audit H-02 closure).

The proxy lives at ``/api/mcp/<path>`` on the Web UI; it resolves the
session cookie to a server-side bearer and forwards to the configured
MCP origin. These tests cover:

* unauthenticated access fails closed (401)
* a known sid forwards with the correct ``Authorization: Bearer …``
  header attached server-side
* a client-supplied ``Authorization`` header does NOT pass through —
  the attacker cannot steal session bearer slots
* upstream ``Set-Cookie`` headers are stripped before returning to
  the browser (defense in depth: a misconfigured MCP build mustn't
  be able to clobber the Web UI session cookie)
* upstream connection failures translate to 502 (not 500)
* CSRF middleware still applies — POST without ``X-SACP-Request: 1``
  is rejected before the proxy body runs
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.web_ui.auth import _make_cookie_value
from src.web_ui.session_store import get_session_store

_SECURE_KEY = Fernet.generate_key().decode()
_COOKIE_KEY = "test-cookie-key-with-at-least-thirty-two-chars-of-entropy-xyz"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_ENCRYPTION_KEY", _SECURE_KEY)
    monkeypatch.setenv("SACP_WEB_UI_COOKIE_KEY", _COOKIE_KEY)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    monkeypatch.setenv("SACP_WEB_UI_MCP_ORIGIN", "http://upstream.test")


def _app():  # type: ignore[no-untyped-def]
    from src.web_ui.app import create_web_app

    return create_web_app()


def _patched_proxy_client(transport: httpx.MockTransport):
    """Patch httpx.AsyncClient inside the proxy module to use our transport."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    return patch("src.web_ui.proxy.httpx.AsyncClient", side_effect=factory)


def test_proxy_rejects_missing_cookie() -> None:
    """No cookie → 401 before the upstream call fires."""
    with TestClient(_app()) as client:
        response = client.get("/api/mcp/tools/anything")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_proxy_rejects_unknown_sid() -> None:
    """A signed cookie with an sid not in the store → 401, no upstream hit."""
    cookie = _make_cookie_value("never-issued-sid")
    with TestClient(_app()) as client:
        client.cookies.set("sacp_ui_token", cookie)
        response = client.get("/api/mcp/tools/anything")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_proxy_attaches_session_bearer_to_upstream() -> None:
    """A live session forwards with Authorization: Bearer <session-bearer>.

    Audit H-02: the bearer never leaves the server. The proxy injects it
    server-side from the session store; the client never sees it and
    cannot supply its own.
    """
    store = get_session_store()
    sid = await store.create("pid-1", "ses-1", "real-bearer-from-store")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True, "echo": "ack"})

    try:
        with (
            _patched_proxy_client(httpx.MockTransport(handler)),
            TestClient(_app()) as client,
        ):
            client.cookies.set("sacp_ui_token", _make_cookie_value(sid))
            response = client.get("/api/mcp/tools/session/list_summaries")

        assert response.status_code == 200
        assert response.json() == {"ok": True, "echo": "ack"}
        assert len(captured) == 1
        forwarded = captured[0]
        assert forwarded.headers.get("authorization") == "Bearer real-bearer-from-store"
        assert forwarded.url.path == "/tools/session/list_summaries"
    finally:
        await store.delete(sid)


@pytest.mark.asyncio
async def test_proxy_overrides_client_supplied_authorization() -> None:
    """A browser-side Authorization header MUST NOT reach upstream.

    Without this, an attacker on a compromised SPA could use the proxy
    as an oracle to test stolen bearers from elsewhere.
    """
    store = get_session_store()
    sid = await store.create("pid-2", "ses-2", "session-bearer")
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    try:
        with (
            _patched_proxy_client(httpx.MockTransport(handler)),
            TestClient(_app()) as client,
        ):
            client.cookies.set("sacp_ui_token", _make_cookie_value(sid))
            response = client.get(
                "/api/mcp/tools/anything",
                headers={"Authorization": "Bearer attacker-supplied"},
            )

        assert response.status_code == 200
        forwarded = captured[0]
        assert forwarded.headers.get("authorization") == "Bearer session-bearer"
    finally:
        await store.delete(sid)


@pytest.mark.asyncio
async def test_proxy_strips_set_cookie_from_upstream_response() -> None:
    """Upstream Set-Cookie must not flow back to the browser.

    Defense in depth: a misconfigured or compromised MCP build mustn't
    be able to overwrite the Web UI's HttpOnly session cookie.
    """
    store = get_session_store()
    sid = await store.create("pid-3", "ses-3", "bearer-3")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True},
            headers={"set-cookie": "evil=1; Path=/"},
        )

    try:
        with (
            _patched_proxy_client(httpx.MockTransport(handler)),
            TestClient(_app()) as client,
        ):
            client.cookies.set("sacp_ui_token", _make_cookie_value(sid))
            response = client.get("/api/mcp/tools/anything")

        assert response.status_code == 200
        # Web UI may set its own Set-Cookie via security middleware; the
        # critical assertion is that "evil=1" did NOT flow through.
        for header_value in response.headers.get_list("set-cookie"):
            assert "evil=1" not in header_value
    finally:
        await store.delete(sid)


@pytest.mark.asyncio
async def test_proxy_returns_502_on_upstream_unreachable() -> None:
    """A connection error to upstream surfaces as 502, not 500."""
    store = get_session_store()
    sid = await store.create("pid-4", "ses-4", "bearer-4")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("upstream down")

    try:
        with (
            _patched_proxy_client(httpx.MockTransport(handler)),
            TestClient(_app()) as client,
        ):
            client.cookies.set("sacp_ui_token", _make_cookie_value(sid))
            response = client.get("/api/mcp/tools/anything")
        assert response.status_code == 502
    finally:
        await store.delete(sid)


@pytest.mark.asyncio
async def test_proxy_csrf_rejects_post_without_header() -> None:
    """The Web UI CSRF middleware applies to /api/mcp/* mutations.

    The SPA always adds X-SACP-Request: 1; a cross-origin attacker
    cannot. POST without the header fails BEFORE the upstream is
    dialed.
    """
    store = get_session_store()
    sid = await store.create("pid-5", "ses-5", "bearer-5")
    upstream_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upstream_called
        upstream_called = True
        return httpx.Response(200)

    try:
        with (
            _patched_proxy_client(httpx.MockTransport(handler)),
            TestClient(_app()) as client,
        ):
            client.cookies.set("sacp_ui_token", _make_cookie_value(sid))
            response = client.post("/api/mcp/tools/session/pause", json={})
        assert response.status_code == 403
        assert upstream_called is False
    finally:
        await store.delete(sid)


_BOOTSTRAP_PATHS = [
    "tools/session/create",
    "tools/session/request_join",
    "tools/session/redeem_invite",
]


@pytest.mark.parametrize("path", _BOOTSTRAP_PATHS)
def test_proxy_bootstrap_paths_forward_without_cookie(path: str) -> None:
    """The pre-auth landing-screen calls forward without an Authorization.

    The SPA invokes these from the unauthenticated landing screen — no
    cookie exists yet. Gating them behind a session deadlocks the
    bootstrap. The upstream MCP routes are public by design.
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"auth_token": "issued-by-upstream"})

    with (
        _patched_proxy_client(httpx.MockTransport(handler)),
        TestClient(_app()) as client,
    ):
        response = client.post(
            f"/api/mcp/{path}",
            json={"display_name": "Facilitator-test"},
            headers={"X-SACP-Request": "1"},
        )

    assert response.status_code == 200
    assert response.json() == {"auth_token": "issued-by-upstream"}
    assert len(captured) == 1
    assert "authorization" not in {k.lower() for k in captured[0].headers}
    assert captured[0].url.path == f"/{path}"


@pytest.mark.parametrize(
    "path",
    [
        "tools/session/create/extra",
        "tools/session/createX",
        "tools/session/create/",
        "tools/session/Create",
        "prefix/tools/session/create",
    ],
)
def test_proxy_bootstrap_allowlist_is_exact_match(path: str) -> None:
    """Near-miss paths must NOT inherit the unauthenticated bootstrap pass.

    The allowlist is a frozenset of exact strings. This test pins that
    semantic so a future refactor (e.g. swapping `in` for `startswith`)
    cannot silently turn `/api/mcp/tools/session/create/anything` into
    a public endpoint.
    """
    upstream_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upstream_called
        upstream_called = True
        return httpx.Response(200)

    with (
        _patched_proxy_client(httpx.MockTransport(handler)),
        TestClient(_app()) as client,
    ):
        response = client.post(
            f"/api/mcp/{path}",
            json={},
            headers={"X-SACP-Request": "1"},
        )

    assert response.status_code == 401
    assert upstream_called is False


@pytest.mark.parametrize("path", _BOOTSTRAP_PATHS)
def test_proxy_bootstrap_paths_strip_client_authorization(path: str) -> None:
    """A client-supplied Authorization on a bootstrap path is stripped.

    Otherwise the proxy could be used as an oracle: attacker fires a
    stolen bearer at `/api/mcp/tools/session/create` and reads the
    upstream response to confirm the bearer is valid. Strip it on the
    way through so the upstream sees the same shape as a legitimate
    pre-auth call.
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"auth_token": "ok"})

    with (
        _patched_proxy_client(httpx.MockTransport(handler)),
        TestClient(_app()) as client,
    ):
        response = client.post(
            f"/api/mcp/{path}",
            json={"display_name": "Facilitator-test"},
            headers={
                "X-SACP-Request": "1",
                "Authorization": "Bearer attacker-supplied",
            },
        )

    assert response.status_code == 200
    assert "authorization" not in {k.lower() for k in captured[0].headers}
