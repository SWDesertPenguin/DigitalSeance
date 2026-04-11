"""Alembic migration environment for raw-SQL migrations with asyncpg."""

from __future__ import annotations

import os

import asyncpg

from alembic import context


def _get_database_url() -> str:
    """Read database URL from environment."""
    url = os.environ.get("SACP_DATABASE_URL", "")
    if not url:
        msg = "SACP_DATABASE_URL not set"
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
