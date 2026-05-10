# SPDX-License-Identifier: AGPL-3.0-or-later

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

from src.accounts import should_mount_account_router
from src.accounts.service import AccountService
from src.auth.service import AuthService
from src.config import load_settings
from src.database.connection import close_pool, create_pool
from src.mcp_server.sse import ConnectionManager, get_connection_manager
from src.repositories.account_repo import AccountRepository
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.log_repo import LogRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.register_repo import RegisterRepository
from src.repositories.review_gate_repo import ReviewGateRepository
from src.repositories.session_repo import SessionRepository
from src.web_ui.session_store import SessionStore, get_session_store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharedServices:
    """Services attached to app.state on the Web UI app.

    Spec 023: ``account_service`` is populated only when the master
    switch + topology gate (research §12, FR-018) permit mounting the
    account router. Off-state leaves the field ``None`` so attaching
    to ``app.state.account_service`` is a no-op and the route handlers'
    503 fall-through stays out of reach behind the route-not-found
    404.
    """

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
    register_repo: RegisterRepository
    session_store: SessionStore
    account_service: AccountService | None = None


def build_services(pool: asyncpg.Pool, encryption_key: str) -> SharedServices:
    """Construct a SharedServices record against an existing pool."""
    log_repo = LogRepository(pool)
    session_store = get_session_store()
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
        log_repo=log_repo,
        register_repo=RegisterRepository(pool),
        session_store=session_store,
        account_service=_maybe_build_account_service(
            pool=pool, log_repo=log_repo, session_store=session_store
        ),
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
    app.state.register_repo = services.register_repo
    app.state.session_store = services.session_store
    app.state.account_service = services.account_service


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
    pool = mcp_app.state.pool
    log_repo = mcp_app.state.log_repo
    session_store = get_session_store()
    account_service = _maybe_build_account_service(
        pool=pool, log_repo=log_repo, session_store=session_store
    )
    services = SharedServices(
        pool=pool,
        encryption_key=_resolve_encryption_key(mcp_app),
        connection_manager=mcp_app.state.connection_manager,
        auth_service=mcp_app.state.auth_service,
        session_repo=mcp_app.state.session_repo,
        participant_repo=mcp_app.state.participant_repo,
        message_repo=mcp_app.state.message_repo,
        interrupt_repo=mcp_app.state.interrupt_repo,
        review_gate_repo=mcp_app.state.review_gate_repo,
        log_repo=log_repo,
        register_repo=mcp_app.state.register_repo,
        session_store=session_store,
        account_service=account_service,
    )
    attach_to_app(web_app, services)


def _maybe_build_account_service(
    *,
    pool: asyncpg.Pool,
    log_repo: LogRepository,
    session_store: SessionStore,
) -> AccountService | None:
    """Construct the AccountService only when the mount gate passes."""
    if not should_mount_account_router():
        return None
    return AccountService(
        account_repo=AccountRepository(pool),
        log_repo=log_repo,
        session_store=session_store,
    )


def _resolve_encryption_key(mcp_app: FastAPI) -> str:
    """Read the encryption key from the MCP app, falling back to settings."""
    if hasattr(mcp_app.state, "encryption_key"):
        return mcp_app.state.encryption_key
    return load_settings().encryption.key
