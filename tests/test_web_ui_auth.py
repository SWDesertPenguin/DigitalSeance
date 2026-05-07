"""Web UI auth-path coverage.

Covers:

* spec 002 / audit H-01 — `_authenticate_or_raise` returns only the
  generic `"IP binding mismatch"` detail in the 403 body when
  `IPBindingMismatchError` fires; never echoes the bound IP, the
  request IP, or any other fragment of the underlying exception. Pairs
  with the MCP equivalent in `src/mcp_server/middleware.py`.
* audit H-02 / M-08 — the signed session cookie carries an opaque sid
  only; the bearer + (participant_id, session_id) binding lives in
  the server-side `SessionStore`. The cookie is signature-stable but
  payload-opaque: a cookie-jar exfiltration recovers no token.
* audit M-02 — cookie signing uses `SACP_WEB_UI_COOKIE_KEY`, distinct
  from `SACP_ENCRYPTION_KEY`. Forging a cookie with the encryption
  key alone fails closed.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException

from src.repositories.errors import (
    AuthRequiredError,
    IPBindingMismatchError,
    TokenExpiredError,
    TokenInvalidError,
)
from src.web_ui.auth import (
    _authenticate_or_raise,
    _make_cookie_value,
    _parse_cookie_value,
)
from src.web_ui.session_store import SessionStore

_COOKIE_KEY = "test-cookie-key-with-at-least-thirty-two-chars-of-entropy-xyz"
_OTHER_KEY = "different-cookie-key-also-thirty-two-chars-or-more-of-entropy"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_WEB_UI_COOKIE_KEY", _COOKIE_KEY)


class _FakeAuthService:
    """Stand-in for AuthService — raises whatever exc is constructed with."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def authenticate(self, token: str, client_ip: str) -> None:
        raise self._exc


class _FakeClient:
    host = "192.0.2.1"  # RFC 5737 TEST-NET-1


class _FakeRequest:
    """Just enough Request shape for _authenticate_or_raise."""

    client = _FakeClient()


@pytest.mark.asyncio
async def test_ip_binding_mismatch_403_omits_ip_fragments() -> None:
    """403 detail must be the generic constant — no bound-IP leak (H-01)."""
    leaky = IPBindingMismatchError(
        "Session bound to 198.51.100.42, request from 203.0.113.7",
    )
    service = _FakeAuthService(leaky)

    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "IP binding mismatch"
    detail = str(exc_info.value.detail)
    assert "198.51.100.42" not in detail
    assert "203.0.113.7" not in detail
    assert "Session bound to" not in detail


@pytest.mark.asyncio
async def test_token_expired_translates_to_401() -> None:
    """Sanity check the expired-token path is unchanged by the H-01 fix."""
    service = _FakeAuthService(TokenExpiredError("expired"))
    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token expired"


@pytest.mark.asyncio
async def test_invalid_token_translates_to_401() -> None:
    """Sanity check the invalid-token path is unchanged."""
    service = _FakeAuthService(TokenInvalidError("invalid"))
    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_auth_required_translates_to_401() -> None:
    """Sanity check the missing-token path is unchanged."""
    service = _FakeAuthService(AuthRequiredError("required"))
    with pytest.raises(HTTPException) as exc_info:
        await _authenticate_or_raise(service, "fake-token", _FakeRequest())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ---------------------------------------------------------------------------
# H-02 / M-08 — cookie payload carries no bearer
# ---------------------------------------------------------------------------


def _decode_signed_payload(signed: str) -> dict:
    """Best-effort decode of an itsdangerous URL-safe-base64 payload.

    itsdangerous concatenates `payload.timestamp.sig`, base64url-encodes
    each segment, and joins them with `.`. The first segment is the
    bare JSON payload — recoverable without the signing key, which is
    exactly the H-02 leak vector we're locking down.
    """
    body_seg = signed.split(".", 1)[0]
    pad = "=" * (-len(body_seg) % 4)
    raw = base64.urlsafe_b64decode(body_seg + pad)
    return json.loads(raw)


def test_cookie_payload_contains_only_opaque_sid() -> None:
    """Audit H-02: the cookie does not carry the bearer in any form.

    A signed (but not encrypted) cookie payload is base64-readable to
    anyone with the cookie value. After this fix the only plaintext
    field is the opaque sid; the bearer never enters the cookie.
    """
    cookie = _make_cookie_value("opaque-sid-xyz")
    payload = _decode_signed_payload(cookie)

    assert payload == {"sid": "opaque-sid-xyz"}
    assert "tok" not in payload
    assert "token" not in payload
    assert "bearer" not in payload
    assert "pid" not in payload
    assert "participant_id" not in payload


def test_cookie_round_trip_returns_same_sid() -> None:
    """A cookie minted with sid X parses back to X."""
    cookie = _make_cookie_value("sid-roundtrip")
    assert _parse_cookie_value(cookie) == "sid-roundtrip"


def test_cookie_signed_with_encryption_key_fails_to_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit M-02: cookies signed with the wrong key are rejected.

    Pre-fix the cookie signer reused `SACP_ENCRYPTION_KEY`; an attacker
    who lifted the encryption key (e.g. for at-rest decryption) could
    also forge cookies. After M-02 the cookie key is independent —
    cookies signed with any other key fail signature verification.
    """
    monkeypatch.setenv("SACP_WEB_UI_COOKIE_KEY", _OTHER_KEY)
    forged = _make_cookie_value("forged-sid")
    monkeypatch.setenv("SACP_WEB_UI_COOKIE_KEY", _COOKIE_KEY)

    with pytest.raises(HTTPException) as exc_info:
        _parse_cookie_value(forged)
    assert exc_info.value.status_code == 401


def test_cookie_with_missing_sid_raises_401() -> None:
    """A signed cookie whose payload omits sid is rejected (defense in depth)."""
    import itsdangerous

    signer = itsdangerous.URLSafeTimedSerializer(_COOKIE_KEY, salt="sacp-ui-cookie-v2")
    cookie = signer.dumps({"unrelated": "field"})

    with pytest.raises(HTTPException) as exc_info:
        _parse_cookie_value(cookie)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Cookie Secure flag — auto-detect from request scheme
# ---------------------------------------------------------------------------


class _SchemeRequest:
    """Minimal Request stand-in for `_secure_cookie_flag` unit coverage."""

    def __init__(self, scheme: str, forwarded_proto: str | None = None) -> None:
        from types import SimpleNamespace

        self.url = SimpleNamespace(scheme=scheme)
        self.headers = {"x-forwarded-proto": forwarded_proto} if forwarded_proto else {}


def test_secure_flag_set_over_https() -> None:
    """A request that arrived as HTTPS gets a Secure cookie."""
    from src.web_ui.auth import _secure_cookie_flag

    assert _secure_cookie_flag(_SchemeRequest("https")) is True


def test_secure_flag_omitted_over_http() -> None:
    """A LAN/HTTP request gets a non-Secure cookie so the browser will send it.

    Pre-fix the Secure flag was on by default; an HTTP-on-LAN deploy
    set the cookie but the browser refused to return it, deadlocking
    every cookie-authed call (proxy 401, WS 4401).
    """
    from src.web_ui.auth import _secure_cookie_flag

    assert _secure_cookie_flag(_SchemeRequest("http")) is False


def test_secure_flag_env_override_forces_insecure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SACP_WEB_UI_INSECURE_COOKIES=1 wins over an HTTPS request."""
    from src.web_ui.auth import _secure_cookie_flag

    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    assert _secure_cookie_flag(_SchemeRequest("https")) is False


def test_secure_flag_honors_x_forwarded_proto_when_trust_proxy_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reverse-proxy TLS termination: inner request is HTTP, XFP says HTTPS."""
    from src.web_ui.auth import _secure_cookie_flag

    monkeypatch.setenv("SACP_TRUST_PROXY", "1")
    request = _SchemeRequest("http", forwarded_proto="https")
    assert _secure_cookie_flag(request) is True


def test_secure_flag_ignores_x_forwarded_proto_without_trust_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without TRUST_PROXY a hostile client cannot upgrade the perceived scheme."""
    from src.web_ui.auth import _secure_cookie_flag

    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    request = _SchemeRequest("http", forwarded_proto="https")
    assert _secure_cookie_flag(request) is False


def test_secure_flag_xfp_takes_rightmost_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxies append to XFF/XFP; the rightmost value reflects the trusted hop."""
    from src.web_ui.auth import _secure_cookie_flag

    monkeypatch.setenv("SACP_TRUST_PROXY", "1")
    # An attacker upstream of the trusted proxy claims https; the proxy then
    # appends its actual view (http). Rightmost wins, so result is False.
    request = _SchemeRequest("http", forwarded_proto="https, http")
    assert _secure_cookie_flag(request) is False


# ---------------------------------------------------------------------------
# Shared client-IP extraction — applies to /login + WS upgrade
# ---------------------------------------------------------------------------


class _ConnectionLike:
    """Duck-typed Request / WebSocket: has .client.host and .headers."""

    def __init__(self, host: str | None, xff: str | None = None) -> None:
        from types import SimpleNamespace

        self.client = SimpleNamespace(host=host) if host is not None else None
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}


def test_extract_client_ip_returns_direct_without_trust_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default deployment: ignore XFF, use the real socket peer."""
    from src.web_ui.auth import extract_client_ip

    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    conn = _ConnectionLike("203.0.113.213", xff="9.9.9.9")
    assert extract_client_ip(conn) == "203.0.113.213"


def test_extract_client_ip_uses_rightmost_xff_with_trust_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behind a trusted reverse proxy, XFF carries the real user IP."""
    from src.web_ui.auth import extract_client_ip

    monkeypatch.setenv("SACP_TRUST_PROXY", "1")
    conn = _ConnectionLike("172.20.0.5", xff="203.0.113.213, 10.0.0.1")
    assert extract_client_ip(conn) == "10.0.0.1"


def test_extract_client_ip_falls_back_to_direct_with_empty_xff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TRUST_PROXY=1 but no/empty XFF: still return the direct peer."""
    from src.web_ui.auth import extract_client_ip

    monkeypatch.setenv("SACP_TRUST_PROXY", "1")
    assert extract_client_ip(_ConnectionLike("172.20.0.5")) == "172.20.0.5"
    assert extract_client_ip(_ConnectionLike("172.20.0.5", xff="")) == "172.20.0.5"


def test_extract_client_ip_handles_missing_client_attr() -> None:
    """A connection with no client (e.g. asgi lifespan tests) returns 'unknown'."""
    from src.web_ui.auth import extract_client_ip

    assert extract_client_ip(_ConnectionLike(None)) == "unknown"


def test_extract_client_ip_does_not_auto_trust_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Web UI auth surfaces (login, WS) are user-facing; loopback is never legit.

    Distinct from the MCP middleware which DOES auto-trust loopback because
    its loopback caller is the in-container proxy hop. /login and /ws are
    only ever reached by the browser; on-host XFF spoofing here would let
    an on-host attacker forge the bound IP at /login, so don't open it.
    """
    from src.web_ui.auth import extract_client_ip

    monkeypatch.delenv("SACP_TRUST_PROXY", raising=False)
    conn = _ConnectionLike("127.0.0.1", xff="203.0.113.213")
    assert extract_client_ip(conn) == "127.0.0.1"


# ---------------------------------------------------------------------------
# Session store unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_store_create_get_delete_roundtrip() -> None:
    """Create returns an opaque sid; get returns the entry; delete drops it."""
    store = SessionStore()
    sid = await store.create("pid-1", "ses-1", "bearer-1")
    assert isinstance(sid, str)
    assert len(sid) >= 32  # token_urlsafe(32) is always >= 43 chars

    entry = await store.get(sid)
    assert entry is not None
    assert entry.participant_id == "pid-1"
    assert entry.session_id == "ses-1"
    assert entry.bearer == "bearer-1"

    await store.delete(sid)
    assert await store.get(sid) is None


@pytest.mark.asyncio
async def test_session_store_delete_is_idempotent() -> None:
    """Deleting an unknown sid is a no-op."""
    store = SessionStore()
    await store.delete("never-existed")  # must not raise


@pytest.mark.asyncio
async def test_session_store_expires_past_ttl() -> None:
    """An entry past TTL is purged on next get and returns None."""
    store = SessionStore(ttl_seconds=0)
    sid = await store.create("pid", "ses", "bearer")
    # ttl=0 → any access counts as expired → entry purged + None returned.
    assert await store.get(sid) is None


# ---------------------------------------------------------------------------
# H-02 — /me + /login no longer hand the bearer to JS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whoami_response_omits_bearer() -> None:
    """Audit H-02: /me must not return the bearer token to JS.

    With the same-origin proxy carrying the bearer server-side, the
    SPA never needs the bearer in JS memory. /me's response must
    therefore not include any token-shaped field that an XSS could
    exfiltrate.
    """
    from types import SimpleNamespace

    from src.web_ui.auth import whoami

    fake_participant = SimpleNamespace(
        id="pid-7",
        session_id="ses-7",
        role="facilitator",
    )
    payload = await whoami(participant=fake_participant)

    assert payload["participant_id"] == "pid-7"
    assert payload["session_id"] == "ses-7"
    assert payload["role"] == "facilitator"
    assert "token" not in payload
    assert "bearer" not in payload
    # No field carries the bearer under any name.
    for value in payload.values():
        assert value != "any-token-value"
        if isinstance(value, str):
            assert not value.startswith("Bearer ")
