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

# Content-Security-Policy tuned for the CDN-loaded SPA. We allow unpkg +
# jsdelivr for scripts because index.html loads React / Babel / marked /
# DOMPurify from those origins with SRI integrity (T204).
#
# connect-src intentionally allows ``http:`` / ``https:`` / ``ws:`` /
# ``wss:`` as schemes because the SPA fetches to the MCP server on a
# sibling port (8750) — a strictly-enumerated host+port list would
# couple CSP to deployment topology. Phase 6 (US8) can tighten this
# when we formalize the allowed MCP origin (FR-006).
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; "
    "connect-src 'self' http: https: ws: wss:; "
    "font-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

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


class CSRFHeaderMiddleware(BaseHTTPMiddleware):
    """Reject mutations missing the custom double-submit CSRF header.

    Browsers send the token cookie automatically, but cross-origin XHR
    cannot set a custom header without a preflight that our strict CORS
    rejects. That asymmetry defeats classic CSRF while keeping the
    cookie-based session model ergonomic.
    """

    async def dispatch(self, request: Request, call_next: _NextCall) -> Response:
        if request.method in _MUTATING_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
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
