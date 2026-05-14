# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fernet-encrypted opaque refresh tokens with rotation + replay detection.

Spec 030 Phase 4 FR-079, FR-080.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import asyncpg
from cryptography.fernet import Fernet

from src.mcp_protocol.auth import token_family as _family_mod

_INSERT_SQL = """
    INSERT INTO oauth_refresh_tokens
        (token_hash, encrypted_token, participant_id, client_id, scope,
         issued_at, expires_at, family_id, parent_token_hash)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
"""

_LOOKUP_SQL = """
    SELECT token_hash, participant_id, client_id, scope, family_id,
           rotated_at, revoked_at, expires_at
    FROM oauth_refresh_tokens
    WHERE token_hash = $1
"""

_MARK_ROTATED_SQL = """
    UPDATE oauth_refresh_tokens SET rotated_at = $2 WHERE token_hash = $1
"""


def _fernet() -> Fernet:
    key = os.environ.get("SACP_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("SACP_ENCRYPTION_KEY not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _token_hash(cleartext: str) -> str:
    return hashlib.sha256(cleartext.encode("ascii")).hexdigest()


def _ttl_days() -> int:
    val = os.environ.get("SACP_OAUTH_REFRESH_TOKEN_TTL_DAYS", "30")
    try:
        return max(1, min(365, int(val)))
    except (ValueError, TypeError):
        return 30


async def issue_refresh_token(
    conn: asyncpg.Connection,
    client_id: str,
    participant_id: str,
    scope: list[str],
    family_id: str,
    parent_hash: str | None = None,
) -> tuple[str, str]:
    """Issue a new refresh token. Returns (cleartext, token_hash)."""
    cleartext = secrets.token_urlsafe(32)
    thash = _token_hash(cleartext)
    encrypted = _fernet().encrypt(cleartext.encode("ascii"))
    now = datetime.now(tz=UTC)
    expires = now + timedelta(days=_ttl_days())
    await conn.execute(
        _INSERT_SQL,
        thash,
        encrypted,
        participant_id,
        client_id,
        scope,
        now,
        expires,
        family_id,
        parent_hash,
    )
    return cleartext, thash


async def rotate_refresh_token(
    conn: asyncpg.Connection,
    old_cleartext: str,
    client_id: str,
    participant_id: str,
    scope: list[str],
) -> tuple[str, str] | None:
    """Atomically rotate a refresh token.

    Returns (new_cleartext, new_hash) on success.
    Returns None and revokes the entire family on replay detection.
    """
    old_hash = _token_hash(old_cleartext)
    row = await conn.fetchrow(_LOOKUP_SQL, old_hash)
    if row is None:
        return None

    now = datetime.now(tz=UTC)
    if row["rotated_at"] is not None:
        await _family_mod.revoke_family(
            conn,
            row["family_id"],
            f"replay detected on token_hash={old_hash[:16]}...",
            participant_id=row["participant_id"],
        )
        return None

    if row["revoked_at"] is not None or row["expires_at"] < now:
        return None

    async with conn.transaction():
        await conn.execute(_MARK_ROTATED_SQL, old_hash, now)
        new_cleartext, new_hash = await issue_refresh_token(
            conn,
            client_id,
            participant_id,
            scope,
            family_id=row["family_id"],
            parent_hash=old_hash,
        )
    return new_cleartext, new_hash
