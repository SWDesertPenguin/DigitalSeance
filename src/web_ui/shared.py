"""Shared-services wiring for the Web UI.

The Web UI needs the same pool, auth service, and repositories the MCP
app uses. Rather than creating an entirely separate stack, the MCP app's
lifespan prepares the pool, attaches services to its ``app.state``, and
these helpers hydrate the Web UI's ``app.state`` with the same objects.

When ``src/run_apps.py`` launches both apps in the same process, it calls
``prime_from_mcp_app`` after MCP's startup and before the Web UI begins
serving requests. In standalone dev mode (launching the Web UI by itself)
the Web UI runs its own lifespan and provisions its own pool via
``build_standalone_services``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg
from fastapi import FastAPI

from src.auth.service import AuthService
from src.config import load_settings
from src.database.connection import close_pool, create_pool
from src.mcp_server.sse import ConnectionManager, get_connection_manager
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.log_repo import LogRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.review_gate_repo import ReviewGateRepository
from src.repositories.session_repo import SessionRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharedServices:
    """Services attached to app.state on the Web UI app."""

    pool: asyncpg.Pool
    encryption_key: str
    connection_manager: ConnectionManager
    auth_service: AuthService
    session_repo: SessionRepository
    participant_repo: ParticipantRepository
    message_repo: MessageRepository
    interrupt_repo: InterruptRepository
    review_gate_repo: ReviewGateRepository
    log_repo: LogRepository


def build_services(pool: asyncpg.Pool, encryption_key: str) -> SharedServices:
    """Construct a SharedServices record against an existing pool."""
    return SharedServices(
        pool=pool,
        encryption_key=encryption_key,
        connection_manager=get_connection_manager(),
        auth_service=AuthService(pool, encryption_key=encryption_key),
        session_repo=SessionRepository(pool),
        participant_repo=ParticipantRepository(pool, encryption_key=encryption_key),
        message_repo=MessageRepository(pool),
        interrupt_repo=InterruptRepository(pool),
        review_gate_repo=ReviewGateRepository(pool),
        log_repo=LogRepository(pool),
    )


def attach_to_app(app: FastAPI, services: SharedServices) -> None:
    """Copy services onto app.state so route handlers can read them."""
    app.state.pool = services.pool
    app.state.encryption_key = services.encryption_key
    app.state.connection_manager = services.connection_manager
    app.state.auth_service = services.auth_service
    app.state.session_repo = services.session_repo
    app.state.participant_repo = services.participant_repo
    app.state.message_repo = services.message_repo
    app.state.interrupt_repo = services.interrupt_repo
    app.state.review_gate_repo = services.review_gate_repo
    app.state.log_repo = services.log_repo


async def build_standalone_services() -> SharedServices:
    """Dev-mode fallback: create a fresh pool + services from settings."""
    settings = load_settings()
    pool = await create_pool(settings.database)
    return build_services(pool, settings.encryption.key)


async def close_standalone_services(services: SharedServices) -> None:
    """Tear down a standalone-services bundle (for dev/test use)."""
    await close_pool(services.pool)


def prime_from_mcp_app(web_app: FastAPI, mcp_app: FastAPI) -> None:
    """Copy services from a fully-initialized MCP app onto the Web UI app.

    Used by ``src/run_apps.py`` after the MCP app's startup completes.
    """
    services = SharedServices(
        pool=mcp_app.state.pool,
        encryption_key=mcp_app.state.encryption_key
        if hasattr(mcp_app.state, "encryption_key")
        else load_settings().encryption.key,
        connection_manager=mcp_app.state.connection_manager,
        auth_service=mcp_app.state.auth_service,
        session_repo=mcp_app.state.session_repo,
        participant_repo=mcp_app.state.participant_repo,
        message_repo=mcp_app.state.message_repo,
        interrupt_repo=mcp_app.state.interrupt_repo,
        review_gate_repo=mcp_app.state.review_gate_repo,
        log_repo=mcp_app.state.log_repo,
    )
    attach_to_app(web_app, services)
