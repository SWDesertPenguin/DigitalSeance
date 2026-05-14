# SPDX-License-Identifier: AGPL-3.0-or-later
"""Refresh-token family tracking + replay-triggered revocation. Spec 030 Phase 4 FR-079."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg

_INSERT_FAMILY_SQL = """
    INSERT INTO oauth_token_families
        (family_id, participant_id, client_id, root_token_hash, started_at)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING family_id
"""

_REVOKE_FAMILY_SQL = """
    UPDATE oauth_token_families SET revoked_at = $2 WHERE family_id = $1
"""

_REVOKE_REFRESH_TOKENS_SQL = """
    UPDATE oauth_refresh_tokens SET revoked_at = $2
    WHERE family_id = $1 AND revoked_at IS NULL
"""

_INSERT_SECURITY_EVENT_SQL = """
    INSERT INTO security_events
        (session_id, participant_id, event_type, severity, details, timestamp)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


async def create_family(
    conn: asyncpg.Connection,
    participant_id: str,
    client_id: str,
    root_token_hash: str,
) -> str:
    """Insert an oauth_token_families row; return family_id."""
    family_id = uuid.uuid4().hex
    now = datetime.now(tz=UTC)
    await conn.execute(
        _INSERT_FAMILY_SQL, family_id, participant_id, client_id, root_token_hash, now
    )
    return family_id


async def revoke_family(
    conn: asyncpg.Connection,
    family_id: str,
    reason: str,
    participant_id: str = "",
    session_id: str = "oauth",
) -> None:
    """Revoke an entire token family; emit a security_events row."""
    now = datetime.now(tz=UTC)
    async with conn.transaction():
        await conn.execute(_REVOKE_FAMILY_SQL, family_id, now)
        await conn.execute(_REVOKE_REFRESH_TOKENS_SQL, family_id, now)
        await conn.execute(
            _INSERT_SECURITY_EVENT_SQL,
            session_id,
            participant_id or "system",
            "token_family_revoked_replay_attempt",
            "high",
            reason,
            now,
        )
