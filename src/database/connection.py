# SPDX-License-Identifier: AGPL-3.0-or-later

"""asyncpg connection pool lifecycle management."""

from __future__ import annotations

import asyncpg

from src.config import DatabaseConfig


async def create_pool(config: DatabaseConfig) -> asyncpg.Pool:
    """Create and return a configured asyncpg connection pool."""
    pool = await asyncpg.create_pool(
        dsn=config.url,
        min_size=config.pool_min_size,
        max_size=config.pool_max_size,
    )
    await _apply_timeouts(pool, config)
    return pool


async def _apply_timeouts(
    pool: asyncpg.Pool,
    config: DatabaseConfig,
) -> None:
    """Set statement and idle transaction timeouts on the pool."""
    async with pool.acquire() as conn:
        await conn.execute(f"SET statement_timeout = '{config.statement_timeout_ms}ms'")
        timeout_ms = config.idle_timeout_ms
        await conn.execute(f"SET idle_in_transaction_session_timeout = '{timeout_ms}ms'")


async def close_pool(pool: asyncpg.Pool) -> None:
    """Gracefully close the connection pool."""
    await pool.close()
