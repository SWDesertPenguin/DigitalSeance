# SPDX-License-Identifier: AGPL-3.0-or-later

"""Base repository with asyncpg pool reference and query helpers."""

from __future__ import annotations

from typing import Any

import asyncpg


class BaseRepository:
    """Shared foundation for all repository classes."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _fetch_one(
        self,
        query: str,
        *args: Any,
    ) -> asyncpg.Record | None:
        """Execute a query and return a single record or None."""
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetch_all(
        self,
        query: str,
        *args: Any,
    ) -> list[asyncpg.Record]:
        """Execute a query and return all matching records."""
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(
        self,
        query: str,
        *args: Any,
    ) -> str:
        """Execute a statement and return the status string."""
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def _execute_in_transaction(
        self,
        queries: list[tuple[str, tuple[Any, ...]]],
    ) -> None:
        """Run multiple statements in a single transaction."""
        async with self._pool.acquire() as conn, conn.transaction():
            for query, args in queries:
                await conn.execute(query, *args)
