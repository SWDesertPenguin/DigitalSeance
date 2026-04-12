"""Invite repository — hashed tokens with use limits and expiry."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.repositories.base import BaseRepository
from src.repositories.errors import InviteExhaustedError, InviteExpiredError


@dataclass(frozen=True, slots=True)
class Invite:
    """A session join token stored as hash only."""

    token_hash: str
    session_id: str
    created_by: str
    max_uses: int
    uses: int
    expires_at: datetime | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> Invite:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


class InviteRepository(BaseRepository):
    """Data access for invite creation and redemption."""

    async def create_invite(
        self,
        *,
        session_id: str,
        created_by: str,
        max_uses: int = 1,
        expires_at: datetime | None = None,
    ) -> tuple[Invite, str]:
        """Create an invite. Returns (Invite, plaintext_token)."""
        plaintext = secrets.token_urlsafe(32)
        token_hash = _hash_token(plaintext)
        record = await self._fetch_one(
            _INSERT_SQL,
            token_hash,
            session_id,
            created_by,
            max_uses,
            expires_at,
        )
        return Invite.from_record(record), plaintext

    async def redeem_invite(
        self,
        plaintext_token: str,
    ) -> Invite:
        """Redeem an invite token. Raises on expiry or exhaustion."""
        token_hash = _hash_token(plaintext_token)
        record = await self._fetch_one(
            "SELECT * FROM invites WHERE token_hash = $1",
            token_hash,
        )
        if record is None:
            msg = "Invalid invite token"
            raise InviteExpiredError(msg)
        invite = Invite.from_record(record)
        _validate_invite(invite)
        await self._execute(
            "UPDATE invites SET uses = uses + 1 WHERE token_hash = $1",
            token_hash,
        )
        updated = await self._fetch_one(
            "SELECT * FROM invites WHERE token_hash = $1",
            token_hash,
        )
        return Invite.from_record(updated)

    async def list_invites(
        self,
        session_id: str,
    ) -> list[Invite]:
        """List all invites for a session."""
        rows = await self._fetch_all(
            "SELECT * FROM invites WHERE session_id = $1 ORDER BY created_at",
            session_id,
        )
        return [Invite.from_record(r) for r in rows]


def _hash_token(plaintext: str) -> str:
    """SHA-256 hash a token for storage."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _validate_invite(invite: Invite) -> None:
    """Check expiry and use limits."""
    if invite.expires_at is not None:
        _check_expiry(invite)
    if invite.uses >= invite.max_uses:
        raise InviteExhaustedError("Invite max uses reached")


def _check_expiry(invite: Invite) -> None:
    """Raise if the invite has expired."""

    now = datetime.now(tz=UTC)
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if now > expires:
        raise InviteExpiredError("Invite has expired")


_INSERT_SQL = """
    INSERT INTO invites
        (token_hash, session_id, created_by, max_uses, expires_at)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING *
"""
