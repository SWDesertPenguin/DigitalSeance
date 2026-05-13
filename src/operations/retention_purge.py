# SPDX-License-Identifier: AGPL-3.0-or-later

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


_SCRATCH_PURGE_CANDIDATES_SQL = """
    SELECT n.id, n.session_id, n.account_id, n.actor_participant_id
      FROM facilitator_notes n
      JOIN sessions s ON n.session_id = s.id
     WHERE s.status = 'archived'
       AND s.archived_at IS NOT NULL
       AND s.archived_at < $1
       AND n.account_id IS NOT NULL
"""

_SCRATCH_HARD_DELETE_SQL = "DELETE FROM facilitator_notes WHERE id = $1"

_SCRATCH_PURGE_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action, target_id, previous_value, new_value)
    VALUES ($1, $2, 'facilitator_note_purged_retention', $3, NULL, NULL)
"""


async def purge_facilitator_notes_for_retention(
    pool: asyncpg.Pool,
    retention_days: int,
) -> int:
    """Hard-delete account-scoped notes from archived sessions past the window.

    Spec 024 FR-018 + data-model.md: only account-scoped notes are subject
    to the retention sweep (session-scoped notes are deleted on archive via
    the cascade FK). One ``facilitator_note_purged_retention`` audit row is
    emitted per purged note for forensic reconstructability.
    """
    if retention_days <= 0:
        raise ValueError(f"retention_days must be > 0; got {retention_days}")
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    return await _run_scratch_purge_transaction(pool, cutoff)


async def _run_scratch_purge_transaction(pool: asyncpg.Pool, cutoff: datetime) -> int:
    purged = 0
    async with pool.acquire() as conn, conn.transaction():
        candidates = await conn.fetch(_SCRATCH_PURGE_CANDIDATES_SQL, cutoff)
        for row in candidates:
            await conn.execute(_SCRATCH_HARD_DELETE_SQL, row["id"])
            await conn.execute(
                _SCRATCH_PURGE_AUDIT_SQL,
                row["session_id"],
                row["actor_participant_id"],
                row["id"],
            )
            purged += 1
    return purged
