# SPDX-License-Identifier: AGPL-3.0-or-later

"""Branch ID lookup — resolves session's main branch ID."""

from __future__ import annotations

import asyncpg


async def get_main_branch_id(
    pool: asyncpg.Pool,
    session_id: str,
) -> str:
    """Look up the main branch ID for a session."""
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT id FROM branches WHERE session_id = $1 LIMIT 1",
            session_id,
        )
    return result or "main"
