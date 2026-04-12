"""Auth service — token validation, rotation, revocation, lifecycle."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import asyncpg
import bcrypt

from src.auth.guards import require_facilitator, require_not_self, require_role
from src.models.participant import Participant
from src.repositories.errors import (
    AuthRequiredError,
    IPBindingMismatchError,
    TokenExpiredError,
    TokenInvalidError,
)
from src.repositories.log_repo import LogRepository
from src.repositories.participant_repo import ParticipantRepository

DEFAULT_TOKEN_EXPIRY_DAYS = 30


class AuthService:
    """Orchestrates auth operations across repositories."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        encryption_key: str,
        token_expiry_days: int = DEFAULT_TOKEN_EXPIRY_DAYS,
    ) -> None:
        self._pool = pool
        self._participant_repo = ParticipantRepository(
            pool,
            encryption_key=encryption_key,
        )
        self._log_repo = LogRepository(pool)
        self._token_expiry_days = token_expiry_days

    async def authenticate(
        self,
        token: str | None,
        client_ip: str,
    ) -> Participant:
        """Validate a bearer token and return the participant."""
        if not token:
            raise AuthRequiredError("Authentication token required")
        participant = await _find_by_token(self._pool, token)
        _check_expiry(participant)
        await _check_ip_binding(self._pool, participant, client_ip)
        return participant

    async def approve_participant(
        self,
        *,
        facilitator_id: str,
        session_id: str,
        participant_id: str,
    ) -> Participant:
        """Approve a pending participant (facilitator only)."""
        await require_facilitator(self._pool, session_id, facilitator_id)
        await require_role(self._pool, participant_id, expected="pending")
        result = await self._participant_repo.approve(participant_id)
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="approve_participant",
            target_id=participant_id,
            previous_value="pending",
            new_value="participant",
        )
        return result

    async def reject_participant(
        self,
        *,
        facilitator_id: str,
        session_id: str,
        participant_id: str,
        reason: str = "",
    ) -> None:
        """Reject and remove a pending participant (facilitator only)."""
        await require_facilitator(self._pool, session_id, facilitator_id)
        await require_role(self._pool, participant_id, expected="pending")
        await self._participant_repo.delete_participant(participant_id)
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="reject_participant",
            target_id=participant_id,
            new_value=reason,
        )

    async def rotate_token(
        self,
        participant_id: str,
    ) -> str:
        """Self-rotate token. Returns new plaintext (shown once)."""
        new_token = secrets.token_urlsafe(32)
        new_hash = bcrypt.hashpw(
            new_token.encode(),
            bcrypt.gensalt(),
        ).decode()
        expires_at = _compute_expiry(self._token_expiry_days)
        await self._participant_repo.update_auth_token(
            participant_id,
            new_hash=new_hash,
            expires_at=expires_at,
        )
        return new_token

    async def revoke_token(
        self,
        *,
        facilitator_id: str,
        session_id: str,
        participant_id: str,
    ) -> None:
        """Force-revoke a participant's token (facilitator only)."""
        await require_facilitator(self._pool, session_id, facilitator_id)
        random_hash = bcrypt.hashpw(
            secrets.token_bytes(32),
            bcrypt.gensalt(),
        ).decode()
        await self._participant_repo.update_auth_token(
            participant_id,
            new_hash=random_hash,
            expires_at=None,
        )
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="revoke_token",
            target_id=participant_id,
        )

    async def remove_participant(
        self,
        *,
        facilitator_id: str,
        session_id: str,
        participant_id: str,
        reason: str = "",
    ) -> None:
        """Remove a participant (facilitator only, not self)."""
        await require_facilitator(self._pool, session_id, facilitator_id)
        require_not_self(facilitator_id, participant_id)
        await self._participant_repo.depart_participant(participant_id)
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="remove_participant",
            target_id=participant_id,
            new_value=reason,
        )

    async def transfer_facilitator(
        self,
        *,
        facilitator_id: str,
        session_id: str,
        target_id: str,
    ) -> None:
        """Transfer facilitator role to another active participant."""
        await require_facilitator(self._pool, session_id, facilitator_id)
        await require_role(self._pool, target_id, expected="participant")
        async with self._pool.acquire() as conn, conn.transaction():
            await _do_transfer(conn, facilitator_id, target_id, session_id)
        await self._log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="transfer_facilitator",
            target_id=target_id,
            previous_value=facilitator_id,
            new_value=target_id,
        )


async def _find_by_token(
    pool: asyncpg.Pool,
    token: str,
) -> Participant:
    """Find the participant matching this token via bcrypt scan."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM participants" " WHERE auth_token_hash IS NOT NULL",
        )
    for row in rows:
        if bcrypt.checkpw(token.encode(), row["auth_token_hash"].encode()):
            return Participant.from_record(row)
    raise TokenInvalidError("Invalid authentication token")


def _check_expiry(participant: Participant) -> None:
    """Raise TokenExpiredError if the token has expired."""
    expires = getattr(participant, "token_expires_at", None)
    if expires is None:
        return
    now = datetime.utcnow()  # noqa: DTZ003
    if hasattr(expires, "tzinfo") and expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    if now > expires:
        raise TokenExpiredError("Authentication token has expired")


async def _check_ip_binding(
    pool: asyncpg.Pool,
    participant: Participant,
    client_ip: str,
) -> None:
    """Check IP binding; bind if first auth, reject if mismatch."""
    bound = getattr(participant, "bound_ip", None)
    if bound is None:
        await _bind_ip(pool, participant.id, client_ip)
        return
    if bound != client_ip:
        raise IPBindingMismatchError(
            f"Session bound to {bound}, request from {client_ip}",
        )


async def _bind_ip(
    pool: asyncpg.Pool,
    participant_id: str,
    ip: str,
) -> None:
    """Bind a participant's session to a client IP."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET bound_ip = $1 WHERE id = $2",
            ip,
            participant_id,
        )


def _compute_expiry(days: int) -> datetime:
    """Calculate expiry timestamp from now (naive UTC for PostgreSQL)."""
    return datetime.utcnow() + timedelta(days=days)  # noqa: DTZ003


async def _do_transfer(
    conn: asyncpg.Connection,
    old_facilitator: str,
    new_facilitator: str,
    session_id: str,
) -> None:
    """Execute the facilitator transfer atomically."""
    await conn.execute(
        "UPDATE participants SET role = 'participant' WHERE id = $1",
        old_facilitator,
    )
    await conn.execute(
        "UPDATE participants SET role = 'facilitator' WHERE id = $1",
        new_facilitator,
    )
    await conn.execute(
        "UPDATE sessions SET facilitator_id = $1 WHERE id = $2",
        new_facilitator,
        session_id,
    )
