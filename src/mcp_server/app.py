# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI application with SSE endpoint and tool routers."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api_bridge.adapter import initialize_adapter
from src.config import load_settings
from src.database.connection import close_pool, create_pool
from src.mcp_server.sse import get_connection_manager
from src.mcp_server.sse_router import router as sse_router
from src.mcp_server.tools.admin import is_audit_viewer_enabled
from src.mcp_server.tools.admin import router as admin_router
from src.mcp_server.tools.debug import router as debug_router
from src.mcp_server.tools.detection_events import is_detection_history_enabled
from src.mcp_server.tools.detection_events import router as detection_events_router
from src.mcp_server.tools.facilitator import router as facilitator_router
from src.mcp_server.tools.participant import router as participant_router
from src.mcp_server.tools.proposal import router as proposal_router
from src.mcp_server.tools.provider import router as provider_router
from src.mcp_server.tools.session import router as session_router
from src.repositories.errors import (
    NotFacilitatorError,
    ParticipantNotInSessionError,
)

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage app lifecycle — adapter init, pool, services, shutdown.

    Spec 020: env-var validation runs ahead of this hook (in
    `src/run_apps.py`). The lifespan imports the adapter packages so
    `AdapterRegistry` has both `litellm` and `mock` registered before
    `initialize_adapter()` reads `SACP_PROVIDER_ADAPTER`, then
    instantiates the chosen adapter BEFORE the FastAPI router accepts
    connections.
    """
    import src.api_bridge.litellm  # noqa: F401
    import src.api_bridge.mock  # noqa: F401
    from src.api_bridge.adapter import _reset_adapter_for_tests

    # Idempotent in tests: each per-test FastAPI fixture (spec 012 US7)
    # stands the app up fresh, so we clear any prior adapter binding
    # before reinitializing. Production lifespan runs exactly once per
    # process, so the reset is a no-op there.
    _reset_adapter_for_tests()
    initialize_adapter()
    settings = load_settings()
    pool = await create_pool(settings.database)
    app.state.connection_manager = get_connection_manager()
    _attach_services(app, pool, settings.encryption.key)
    yield
    await close_pool(pool)
    _reset_adapter_for_tests()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    OpenAPI / Swagger UI is gated behind SACP_ENABLE_DOCS=1 (006 CHK014).
    Production deployments leave it off so the schema isn't a free
    reconnaissance surface; dev / on-host troubleshooting opts in.
    """
    docs_enabled = os.environ.get("SACP_ENABLE_DOCS", "0") == "1"
    app = FastAPI(
        title="SACP MCP Server",
        version="0.1.0",
        lifespan=_lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    _add_middleware(app)
    _include_routers(app)
    _add_exception_handlers(app)
    return app


async def _handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _handle_not_facilitator(_: Request, exc: NotFacilitatorError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


async def _handle_not_in_session(_: Request, exc: ParticipantNotInSessionError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all 500 handler: generic body, traceback via root logger (006 CHK010)."""
    del exc  # logged via .exception() below from the active context
    logging.getLogger(__name__).exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _add_exception_handlers(app: FastAPI) -> None:
    """Convert auth/guard errors into clean 4xx responses + scrub 500s."""
    app.add_exception_handler(ValueError, _handle_value_error)
    app.add_exception_handler(NotFacilitatorError, _handle_not_facilitator)
    app.add_exception_handler(ParticipantNotInSessionError, _handle_not_in_session)
    app.add_exception_handler(Exception, _handle_unhandled)


def _add_middleware(app: FastAPI) -> None:
    """Add CORS middleware + (optional) network-layer rate limiter.

    Per spec 019 contracts/middleware-ordering.md the
    ``NetworkRateLimitMiddleware`` MUST be the LAST add_middleware call
    (= outermost on the request stack per FastAPI's reverse-order
    semantics) so it runs BEFORE auth / bcrypt / anything else.
    Conditional on ``SACP_NETWORK_RATELIMIT_ENABLED=true`` (FR-014 /
    SC-006: the middleware MUST NOT appear in user_middleware when
    disabled — pre-feature byte-identical).
    """
    cors_env = os.environ.get("SACP_CORS_ORIGINS", "")
    if cors_env:
        origins = [o.strip() for o in cors_env.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        _add_lan_cors(app)
    _add_network_rate_limit(app)


def _add_network_rate_limit(app: FastAPI) -> None:
    """Conditionally register the spec 019 per-IP limiter as outermost."""
    raw_enabled = os.environ.get("SACP_NETWORK_RATELIMIT_ENABLED", "").strip().lower()
    if raw_enabled not in ("true", "1"):
        return
    from src.middleware.network_rate_limit import NetworkRateLimitMiddleware

    rpm = int(os.environ.get("SACP_NETWORK_RATELIMIT_RPM", "60"))
    burst = int(os.environ.get("SACP_NETWORK_RATELIMIT_BURST", "15"))
    max_keys = int(os.environ.get("SACP_NETWORK_RATELIMIT_MAX_KEYS", "100000"))
    raw_trust = (
        os.environ.get(
            "SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS",
            "false",
        )
        .strip()
        .lower()
    )
    trust_forwarded_headers = raw_trust in ("true", "1")
    app.add_middleware(
        NetworkRateLimitMiddleware,
        rpm=rpm,
        burst=burst,
        max_keys=max_keys,
        trust_forwarded_headers=trust_forwarded_headers,
    )
    _log_middleware_order(app)


def _log_middleware_order(app: FastAPI) -> None:
    """Emit the FR-002 introspection line (contracts/middleware-ordering.md).

    Format pinned by contracts/middleware-ordering.md: ``Middleware order
    (outermost first): [Name1, Name2, ...]`` — bracket-list form WITHOUT
    quotes around class names so the caplog regex anchors on a stable
    prefix.
    """
    # FastAPI's add_middleware() prepends to user_middleware (insert at
    # index 0), so user_middleware[0] is the most recently registered =
    # OUTERMOST. The introspection log shows OUTERMOST FIRST, which is
    # the natural list order — no reverse needed.
    outermost_first = [m.cls.__name__ for m in app.user_middleware]
    rendered = "[" + ", ".join(outermost_first) + "]"
    logging.getLogger(__name__).info(
        "Middleware order (outermost first): %s",
        rendered,
    )


def _add_lan_cors(app: FastAPI) -> None:
    """Add CORS with RFC-1918 LAN regex defaults.

    Octet patterns are 0-255 only (006 CHK002): pre-fix the regex matched
    192.168.999.999 and similar invalid octets. The `_OCTET` group below
    accepts 0-255 in a non-capturing alternative.
    """
    octet = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:8750",
            "http://127.0.0.1",
            "http://127.0.0.1:8750",
        ],
        allow_origin_regex=(
            rf"https?://(localhost|127\.0\.0\.1)(:\d+)?"
            rf"|http://192\.168\.{octet}\.{octet}(:\d+)?"
            rf"|http://10\.{octet}\.{octet}\.{octet}(:\d+)?"
        ),
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _include_routers(app: FastAPI) -> None:
    """Register all tool routers."""
    app.include_router(sse_router)
    app.include_router(participant_router)
    app.include_router(facilitator_router)
    app.include_router(session_router)
    app.include_router(proposal_router)
    app.include_router(provider_router)
    app.include_router(debug_router)
    # Spec 029 §FR-018 — master switch hides the audit-log viewer surface
    # at the route layer when SACP_AUDIT_VIEWER_ENABLED is unset/false, so
    # disabled deployments return HTTP 404 from absence of the route rather
    # than a 200 with empty data.
    if is_audit_viewer_enabled():
        app.include_router(admin_router)
    # Spec 022 FR-016 — master switch hides the detection-event history
    # surface at the route layer when SACP_DETECTION_HISTORY_ENABLED is
    # unset/false, so disabled deployments return HTTP 404 from absence
    # of the route rather than a 200 with empty data.
    if is_detection_history_enabled():
        app.include_router(detection_events_router)


def _attach_services(
    app: FastAPI,
    pool: object,
    encryption_key: str,
) -> None:
    """Attach shared services to app state."""
    _attach_auth_and_repos(app, pool, encryption_key)
    _attach_orchestrator(app, pool, encryption_key)


def _attach_auth_and_repos(
    app: FastAPI,
    pool: object,
    encryption_key: str,
) -> None:
    """Attach auth, repos, and rate limiter."""
    from src.auth.service import AuthService
    from src.mcp_server.rate_limiter import RateLimiter
    from src.repositories.interrupt_repo import InterruptRepository
    from src.repositories.invite_repo import InviteRepository
    from src.repositories.log_repo import LogRepository
    from src.repositories.message_repo import MessageRepository
    from src.repositories.participant_repo import ParticipantRepository
    from src.repositories.register_repo import RegisterRepository
    from src.repositories.review_gate_repo import ReviewGateRepository
    from src.repositories.session_repo import SessionRepository

    app.state.pool = pool
    app.state.encryption_key = encryption_key
    app.state.auth_service = AuthService(pool, encryption_key=encryption_key)
    app.state.session_repo = SessionRepository(pool)
    app.state.participant_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    app.state.message_repo = MessageRepository(pool)
    app.state.interrupt_repo = InterruptRepository(pool)
    app.state.invite_repo = InviteRepository(pool)
    app.state.review_gate_repo = ReviewGateRepository(pool)
    app.state.log_repo = LogRepository(pool)
    app.state.register_repo = RegisterRepository(pool)
    app.state.rate_limiter = RateLimiter()


def _attach_orchestrator(
    app: FastAPI,
    pool: object,
    encryption_key: str,
) -> None:
    """Attach conversation loop."""
    from src.orchestrator.loop import ConversationLoop

    app.state.conversation_loop = ConversationLoop(pool, encryption_key=encryption_key)
