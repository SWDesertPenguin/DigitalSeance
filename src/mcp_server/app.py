"""FastAPI application with SSE endpoint and tool routers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import load_settings
from src.database.connection import close_pool, create_pool
from src.mcp_server.tools.facilitator import router as facilitator_router
from src.mcp_server.tools.participant import router as participant_router
from src.mcp_server.tools.session import router as session_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage app lifecycle — pool, services, shutdown."""
    settings = load_settings()
    pool = await create_pool(settings.database)
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
    return app


def _add_middleware(app: FastAPI) -> None:
    """Add CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrictive in production
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _include_routers(app: FastAPI) -> None:
    """Register all tool routers."""
    app.include_router(participant_router)
    app.include_router(facilitator_router)
    app.include_router(session_router)


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
    from src.repositories.message_repo import MessageRepository
    from src.repositories.participant_repo import ParticipantRepository
    from src.repositories.session_repo import SessionRepository

    app.state.pool = pool
    app.state.auth_service = AuthService(pool, encryption_key=encryption_key)
    app.state.session_repo = SessionRepository(pool)
    app.state.participant_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    app.state.message_repo = MessageRepository(pool)
    app.state.interrupt_repo = InterruptRepository(pool)
    app.state.invite_repo = InviteRepository(pool)
    app.state.rate_limiter = RateLimiter()


def _attach_orchestrator(
    app: FastAPI,
    pool: object,
    encryption_key: str,
) -> None:
    """Attach conversation loop."""
    from src.orchestrator.loop import ConversationLoop

    app.state.conversation_loop = ConversationLoop(pool, encryption_key=encryption_key)
