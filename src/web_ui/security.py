"""Security-header + CORS middleware for the Web UI.

FR-001..FR-003 and SR-001..SR-008 require a strict posture: no inline
scripts, no data: images, no wildcard CORS, no caching, and a CSRF
signal on mutations. These helpers wire that into the FastAPI app
factory.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

_NextCall = Callable[[Request], Awaitable[Response]]

CSRF_HEADER = "X-SACP-Request"
CSRF_VALUE = "1"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Content-Security-Policy tuned for the CDN-loaded SPA.
#
# script-src: self + the two pinned CDN origins. ``'unsafe-eval'`` is
# mandatory because Babel Standalone compiles JSX at runtime via
# ``new Function(...)``. ``'unsafe-inline'`` is also required because
# Babel injects the transpiled module back into the DOM as an inline
# ``<script>`` element, which ``script-src-elem`` would otherwise
# block. Trade-off documented in spec SR-001; SRI integrity attributes
# (task T204) are the primary CDN-compromise defense once populated.
#
# connect-src: 'self' + the explicit MCP origin (and its ws/wss
# equivalents) + an explicit Web UI WebSocket origin list. The previous
# scheme-only `ws: wss:` allowed *any* host, which provided a turnkey
# exfiltration channel if any future XSS regression slipped past
# DOMPurify. Both env vars below are space-separated origin lists.
#
# LAN dev operators who set SACP_WEB_UI_MCP_ORIGIN to a LAN address
# should likewise set SACP_WEB_UI_WS_ORIGIN to the matching ws:// for
# the Web UI's own WebSocket — defaults cover loopback only.
_MCP_ORIGIN = os.environ.get(
    "SACP_WEB_UI_MCP_ORIGIN",
    "http://localhost:8750 http://127.0.0.1:8750",
)
_WEB_UI_WS_ORIGIN = os.environ.get(
    "SACP_WEB_UI_WS_ORIGIN",
    "ws://localhost:8751 wss://localhost:8751 ws://127.0.0.1:8751 wss://127.0.0.1:8751",
)


def _http_to_ws(origins: str) -> str:
    """Convert space-separated http(s):// origins to their ws(s):// counterparts."""
    out = []
    for o in origins.split():
        if o.startswith("https://"):
            out.append("wss://" + o[len("https://") :])
        elif o.startswith("http://"):
            out.append("ws://" + o[len("http://") :])
    return " ".join(out)


def _build_csp() -> str:
    """CSP includes a report-uri so violations land in the server log
    instead of being silent (011 §SR-001 / CHK003). The endpoint
    /csp-report (POST) is a stub that 204s the request after logging.
    """
    mcp_ws = _http_to_ws(_MCP_ORIGIN)
    connect_parts = ["'self'", _MCP_ORIGIN, mcp_ws, _WEB_UI_WS_ORIGIN]
    connect = " ".join(p for p in connect_parts if p)
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'unsafe-inline' "
        "https://unpkg.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; "
        f"connect-src {connect}; "
        "font-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "report-uri /csp-report"
    )


_CSP = _build_csp()

_HEADERS = {
    "Content-Security-Policy": _CSP,
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the full security-header set to every response."""

    async def dispatch(self, request: Request, call_next: _NextCall) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response


# CSRF-exempt paths: browsers POST CSP violation reports without our custom
# header (they can't be told to add it), so we exempt the report sink.
_CSRF_EXEMPT_PATHS = frozenset({"/csp-report"})


class CSRFHeaderMiddleware(BaseHTTPMiddleware):
    """Reject mutations missing the custom double-submit CSRF header.

    Browsers send the token cookie automatically, but cross-origin XHR
    cannot set a custom header without a preflight that our strict CORS
    rejects. That asymmetry defeats classic CSRF while keeping the
    cookie-based session model ergonomic.
    """

    async def dispatch(self, request: Request, call_next: _NextCall) -> Response:
        if (
            request.method in _MUTATING_METHODS
            and request.url.path not in _CSRF_EXEMPT_PATHS
            and request.headers.get(CSRF_HEADER) != CSRF_VALUE
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": f"Missing {CSRF_HEADER} header"},
            )
        return await call_next(request)


def add_security_headers(app: FastAPI) -> None:
    """Attach the SecurityHeadersMiddleware."""
    app.add_middleware(SecurityHeadersMiddleware)


def add_csrf_header_check(app: FastAPI) -> None:
    """Attach the CSRFHeaderMiddleware (applies to all mutating methods)."""
    app.add_middleware(CSRFHeaderMiddleware)


def add_strict_cors(app: FastAPI) -> None:
    """Same-origin CORS. SACP_WEB_UI_ALLOWED_ORIGINS overrides for dev."""
    override = os.environ.get("SACP_WEB_UI_ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in override.split(",") if o.strip()] if override else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-SACP-Request"],
    )
