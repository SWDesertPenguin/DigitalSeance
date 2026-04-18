"""FastAPI application with SSE endpoint and tool routers."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import load_settings
from src.database.connection import close_pool, create_pool
from src.mcp_server.sse import ConnectionManager
from src.mcp_server.sse_router import router as sse_router
from src.mcp_server.tools.debug import router as debug_router
from src.mcp_server.tools.facilitator import router as facilitator_router
from src.mcp_server.tools.participant import router as participant_router
from src.mcp_server.tools.session import router as session_router
from src.repositories.errors import NotFacilitatorError

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage app lifecycle — pool, services, shutdown."""
    settings = load_settings()
    pool = await create_pool(settings.database)
    app.state.connection_manager = ConnectionManager()
    _attach_services(app, pool, settings.encryption.key)
    yield
    await close_pool(pool)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="SACP MCP Server",
        version="0.1.0",
        lifespan=_lifespan,
    )
    _add_middleware(app)
    _include_routers(app)
    _add_exception_handlers(app)
    return app


def _add_exception_handlers(app: FastAPI) -> None:
    """Convert auth/guard errors into clean 4xx responses."""

    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    async def not_facilitator(_: Request, exc: NotFacilitatorError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    app.add_exception_handler(ValueError, value_error)
    app.add_exception_handler(NotFacilitatorError, not_facilitator)


def _add_middleware(app: FastAPI) -> None:
    """Add CORS middleware (LAN default, SACP_CORS_ORIGINS override)."""
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


def _add_lan_cors(app: FastAPI) -> None:
    """Add CORS with RFC-1918 LAN regex defaults."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:8750",
            "http://127.0.0.1",
            "http://127.0.0.1:8750",
        ],
        allow_origin_regex=(
            r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
            r"|http://192\.168\.\d+\.\d+(:\d+)?"
            r"|http://10\.\d+\.\d+\.\d+(:\d+)?"
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
    app.include_router(debug_router)


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
    from src.repositories.review_gate_repo import ReviewGateRepository
    from src.repositories.session_repo import SessionRepository

    app.state.pool = pool
    app.state.auth_service = AuthService(pool, encryption_key=encryption_key)
    app.state.session_repo = SessionRepository(pool)
    app.state.participant_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    app.state.message_repo = MessageRepository(pool)
    app.state.interrupt_repo = InterruptRepository(pool)
    app.state.invite_repo = InviteRepository(pool)
    app.state.review_gate_repo = ReviewGateRepository(pool)
    app.state.log_repo = LogRepository(pool)
    app.state.rate_limiter = RateLimiter()


def _attach_orchestrator(
    app: FastAPI,
    pool: object,
    encryption_key: str,
) -> None:
    """Attach conversation loop."""
    from src.orchestrator.loop import ConversationLoop

    app.state.conversation_loop = ConversationLoop(pool, encryption_key=encryption_key)
