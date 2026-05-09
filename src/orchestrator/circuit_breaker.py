# SPDX-License-Identifier: AGPL-3.0-or-later

"""Circuit breaker — auto-pause after consecutive failures."""

from __future__ import annotations

import asyncpg

DEFAULT_THRESHOLD = 3


class CircuitBreaker:
    """Tracks consecutive provider failures per participant."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> None:
        self._pool = pool
        self._threshold = threshold

    async def record_failure(self, participant_id: str) -> bool:
        """Increment failure count. Returns True if now open (paused)."""
        async with self._pool.acquire() as conn:
            count = await _increment_timeouts(conn, participant_id)
        if count >= self._threshold:
            await self._auto_pause(participant_id)
            return True
        return False

    async def record_success(self, participant_id: str) -> None:
        """Reset failure count to zero."""
        async with self._pool.acquire() as conn:
            await _reset_timeouts(conn, participant_id)

    async def is_open(self, participant_id: str) -> bool:
        """Check if circuit is open (participant paused from failures)."""
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT consecutive_timeouts FROM participants WHERE id = $1",
                participant_id,
            )
        return (count or 0) >= self._threshold

    async def _auto_pause(self, participant_id: str) -> None:
        """Pause participant due to consecutive failures."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE participants SET status = 'paused' WHERE id = $1",
                participant_id,
            )


async def _increment_timeouts(
    conn: asyncpg.Connection,
    participant_id: str,
) -> int:
    """Increment and return new consecutive timeout count."""
    return await conn.fetchval(
        "UPDATE participants"
        " SET consecutive_timeouts = consecutive_timeouts + 1"
        " WHERE id = $1"
        " RETURNING consecutive_timeouts",
        participant_id,
    )


async def _reset_timeouts(
    conn: asyncpg.Connection,
    participant_id: str,
) -> None:
    """Reset consecutive timeout count to zero."""
    await conn.execute(
        "UPDATE participants SET consecutive_timeouts = 0 WHERE id = $1",
        participant_id,
    )
