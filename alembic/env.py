# SPDX-License-Identifier: AGPL-3.0-or-later

"""Alembic migration environment for raw-SQL migrations with asyncpg."""

from __future__ import annotations

import os
import urllib.parse

import asyncpg

from alembic import context

# Audit Critical-4: the three runtime-only roles. If a DSN with one of
# these usernames reaches the migration runner, refuse to start -- only
# sacp_admin (or, in dev/legacy paths, the bootstrap superuser) has the
# DDL privileges migrations need.
_RUNTIME_ONLY_ROLES = frozenset({"sacp_app", "sacp_audit_reader", "sacp_cleanup"})


def _get_database_url() -> str:
    """Resolve the migration DSN.

    Priority order:
      1. ``SACP_DATABASE_URL_MIGRATIONS`` -- set by the compose stack's
         ``sacp-migrate`` one-shot service to the sacp_admin DSN.
      2. ``SACP_DATABASE_URL`` -- fallback for non-compose deploys and for
         the runtime container's image-baked ``alembic upgrade head``
         chain (which is a no-op when head is already current).

    Fails closed if neither is set, and rejects DSNs that point at one of
    the runtime-only roles since those roles cannot execute DDL.
    """
    url = os.environ.get("SACP_DATABASE_URL_MIGRATIONS") or os.environ.get("SACP_DATABASE_URL", "")
    if not url:
        msg = "Neither SACP_DATABASE_URL_MIGRATIONS nor SACP_DATABASE_URL set"
        raise OSError(msg)
    parsed = urllib.parse.urlparse(url)
    if parsed.username in _RUNTIME_ONLY_ROLES:
        msg = (
            f"Migration DSN points at runtime role {parsed.username!r}; "
            "migrations need sacp_admin (or the bootstrap superuser in dev)."
        )
        raise OSError(msg)
    return url


def run_migrations_offline() -> None:
    """Run migrations in offline mode (SQL script generation)."""
    context.configure(
        url=_get_database_url(),
        target_metadata=None,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    """Connect via asyncpg and run migrations."""
    url = _get_database_url()
    conn = await asyncpg.connect(url)
    try:
        await conn.reload_schema_state()
    finally:
        await conn.close()


def run_migrations_online() -> None:
    """Run migrations in online mode using synchronous Alembic."""
    from sqlalchemy import create_engine

    url = _get_database_url().replace("postgresql://", "postgresql+psycopg2://")
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
