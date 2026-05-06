"""Retention purge functions for the 001 §FR-019 retention pattern.

Tables that follow the "indefinite by default + operator-driven purge with
reserved env var" pattern delete rows older than an operator-configured
retention window. Operators schedule the purge externally (cron / Ofelia /
k8s CronJob); this module supplies the purge function and the CLI entry
points in `scripts/purge_*.py`.

Per 007 §SC-009 (security_events 90-day default).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg


async def purge_security_events(
    pool: asyncpg.Pool,
    retention_days: int,
) -> int:
    """Delete security_events rows older than retention_days. Returns row count.

    007 §SC-009: bounded retention for the security_events table.
    Cutoff is computed in Python (NOW() - retention_days) so the SQL
    is parameterized — operators don't pass interval strings to the DB.
    """
    if retention_days <= 0:
        raise ValueError(
            f"retention_days must be > 0; got {retention_days}",
        )
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=retention_days)
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM security_events WHERE timestamp < $1",
            cutoff,
        )
    # asyncpg returns "DELETE <n>" as the status string.
    return int(result.split()[-1]) if result.startswith("DELETE ") else 0
