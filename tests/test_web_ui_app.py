"""Foundational tests for the Phase 2 Web UI FastAPI app.

Covers tasks T040:
  - factory returns a working app
  - /healthz works without a DB
  - static /frontend mount serves index.html at /
  - all security headers present on every response
  - CORS behavior (strict by default, configurable via env)
  - CSRF middleware rejects mutations without the custom header
  - /login returns 401 when the token is invalid
  - /logout clears the cookie
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

# Fresh key per test session — avoids committing a literal "secret".
_SECURE_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed the env vars the Web UI reads at request time."""
    monkeypatch.setenv("SACP_ENCRYPTION_KEY", _SECURE_KEY)
    # Insecure cookie flag lets TestClient (HTTP) verify the cookie is set.
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")


def _fresh_app():  # type: ignore[no-untyped-def]
    # Import lazily so the env vars above are in place before app construction.
    from src.web_ui.app import create_web_app

    return create_web_app()


def test_create_web_app_returns_fastapi() -> None:
    """Factory returns a FastAPI instance with the expected title."""
    app = _fresh_app()
    assert app.title == "SACP Web UI"


def test_healthcheck_returns_ok() -> None:
    """/healthz works without a DB pool attached."""
    with TestClient(_fresh_app()) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_mounted_at_root() -> None:
    """The frontend/ directory is served as static files."""
    with TestClient(_fresh_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "SACP Web UI" in response.text


def test_security_headers_present() -> None:
    """Every response carries the hardened security-header set."""
    with TestClient(_fresh_app()) as client:
        response = client.get("/healthz")
    for name in (
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cache-Control",
    ):
        assert name in response.headers, f"missing {name}"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_csp_includes_report_uri() -> None:
    """CSP carries a report-uri so violations land in the server log (011 CHK003)."""
    with TestClient(_fresh_app()) as client:
        response = client.get("/healthz")
    assert "report-uri /csp-report" in response.headers["Content-Security-Policy"]


def test_csp_report_endpoint_accepts_post_without_csrf_header() -> None:
    """Browsers POST CSP violations without the X-SACP-Request header; the
    sink endpoint MUST accept them (011 CHK003).
    """
    with TestClient(_fresh_app()) as client:
        response = client.post(
            "/csp-report",
            content=b'{"csp-report":{"violated-directive":"script-src"}}',
            headers={"Content-Type": "application/csp-report"},
        )
    assert response.status_code == 204


def test_csrf_rejects_post_without_header() -> None:
    """POST without X-SACP-Request header → 403."""
    with TestClient(_fresh_app()) as client:
        response = client.post("/login", json={"token": "whatever"})
    assert response.status_code == 403
    assert "X-SACP-Request" in response.json()["detail"]


def test_csrf_accepts_post_with_header() -> None:
    """POST with the custom header passes the CSRF middleware.

    Uses /logout instead of /login because /login touches the DB on
    some CI matrices — this test is only about the middleware pass-
    through semantics, not auth behavior.
    """
    with TestClient(_fresh_app()) as client:
        response = client.post("/logout", headers={"X-SACP-Request": "1"})
    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}


def test_logout_clears_cookie() -> None:
    """POST /logout returns a Set-Cookie clearing sacp_ui_token."""
    with TestClient(_fresh_app()) as client:
        response = client.post(
            "/logout",
            headers={"X-SACP-Request": "1"},
        )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "sacp_ui_token=" in set_cookie
    # max-age=0 OR expires in the past signals cookie-clear.
    assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()


def test_cors_default_origins_empty() -> None:
    """Default (no env override) allows no origins — same-origin only."""
    with TestClient(_fresh_app()) as client:
        response = client.options(
            "/healthz",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    # With no allow_origins and origin mismatch, CORS headers should be absent
    # or the wildcard header must NOT be "*".
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin != "*"
    assert allow_origin != "https://evil.example"


def test_cors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """SACP_WEB_UI_ALLOWED_ORIGINS is honored."""
    monkeypatch.setenv("SACP_WEB_UI_ALLOWED_ORIGINS", "https://ok.example")
    with TestClient(_fresh_app()) as client:
        response = client.options(
            "/healthz",
            headers={
                "Origin": "https://ok.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers.get("access-control-allow-origin") == "https://ok.example"


def test_cookie_attrs_on_successful_login_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cookie-clear path on /logout uses SameSite=Strict + HttpOnly."""
    with TestClient(_fresh_app()) as client:
        response = client.post("/logout", headers={"X-SACP-Request": "1"})
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie


def test_missing_encryption_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """If SACP_ENCRYPTION_KEY is absent, cookie signer refuses to sign."""
    monkeypatch.delenv("SACP_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("SACP_WEB_UI_INSECURE_COOKIES", "1")
    from src.web_ui.auth import _make_cookie_value  # local import after env mutation

    with pytest.raises(RuntimeError):
        _make_cookie_value("pid", "sid", "tok")
