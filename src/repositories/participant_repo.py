# SPDX-License-Identifier: AGPL-3.0-or-later

"""Participant repository — join, config, encryption, departure."""

from __future__ import annotations

import uuid

import asyncpg
import bcrypt

from src.auth.token_lookup import compute_token_lookup
from src.database.encryption import encrypt_value
from src.models.participant import Participant
from src.repositories.base import BaseRepository


class ParticipantRepository(BaseRepository):
    """Data access for participant CRUD and lifecycle."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        encryption_key: str,
    ) -> None:
        super().__init__(pool)
        self._encryption_key = encryption_key

    async def add_participant(
        self,
        *,
        session_id: str,
        display_name: str,
        provider: str,
        model: str,
        model_tier: str,
        model_family: str,
        context_window: int,
        api_key: str | None = None,
        api_endpoint: str | None = None,
        auth_token: str | None = None,
        budget_hourly: float | None = None,
        budget_daily: float | None = None,
        max_tokens_per_turn: int | None = None,
        auto_approve: bool = False,
        invited_by: str | None = None,
    ) -> tuple[Participant, str | None]:
        """Add a participant, encrypting API key and hashing token."""
        pid = uuid.uuid4().hex[:12]
        role = "participant" if auto_approve else "pending"
        args = (
            pid,
            session_id,
            display_name,
            role,
            provider,
            model,
            model_tier,
            model_family,
            context_window,
            _encrypt_api_key(api_key, self._encryption_key),
            _hash_auth_token(auth_token),
            _lookup_auth_token(auth_token),
            api_endpoint,
            budget_hourly,
            budget_daily,
            invited_by,
            max_tokens_per_turn,
        )
        await self._execute(_INSERT_PARTICIPANT_SQL, *args)
        rec = await self._fetch_one("SELECT * FROM participants WHERE id = $1", pid)
        return Participant.from_record(rec), auth_token

    async def get_participant(
        self,
        participant_id: str,
    ) -> Participant | None:
        """Retrieve a participant by ID."""
        record = await self._fetch_one(
            "SELECT * FROM participants WHERE id = $1",
            participant_id,
        )
        return Participant.from_record(record) if record else None

    async def list_participants(
        self,
        session_id: str,
        *,
        status_filter: str | None = None,
    ) -> list[Participant]:
        """List participants in a session."""
        if status_filter:
            rows = await self._fetch_all(
                "SELECT * FROM participants WHERE session_id = $1 AND status = $2",
                session_id,
                status_filter,
            )
        else:
            rows = await self._fetch_all(
                "SELECT * FROM participants WHERE session_id = $1",
                session_id,
            )
        return [Participant.from_record(r) for r in rows]

    async def depart_participant(
        self,
        participant_id: str,
    ) -> None:
        """Overwrite API key, invalidate token, set offline."""
        overwrite = encrypt_value(
            uuid.uuid4().hex,
            key=self._encryption_key,
        )
        await self._execute(
            """UPDATE participants
               SET api_key_encrypted = $1,
                   auth_token_hash = NULL,
                   auth_token_lookup = NULL,
                   status = 'offline'
               WHERE id = $2""",
            overwrite,
            participant_id,
        )

    async def reset_ai_credentials(
        self,
        participant_id: str,
        *,
        api_key: str | None,
        provider: str | None = None,
        model: str | None = None,
        api_endpoint: str | None = None,
    ) -> None:
        """Rotate an AI's API key in place (optionally swap provider/model/endpoint).

        Keeps the participant row so prior messages stay attributed and the
        turn-loop can dispatch the AI again on the next turn. Clears the
        timeout counter so the circuit breaker doesn't keep skipping the
        AI after a bad-key episode; nulls the old auth_token_hash when the
        key actually rotated so any client still holding the AI's bearer is
        forced to re-mint.

        ``api_key`` may be None — only valid for ollama, which doesn't auth.
        Caller (the MCP handler) enforces "ollama only" for the None case.
        When None, api_key_encrypted stays as-is and auth_token_hash is
        preserved (no rotation = no forced re-mint).
        """
        new_encrypted = (
            _encrypt_api_key(api_key, self._encryption_key) if api_key is not None else None
        )
        await self._execute(
            """UPDATE participants
               SET api_key_encrypted = COALESCE($1, api_key_encrypted),
                   auth_token_hash = CASE WHEN $1 IS NOT NULL
                       THEN NULL ELSE auth_token_hash END,
                   auth_token_lookup = CASE WHEN $1 IS NOT NULL
                       THEN NULL ELSE auth_token_lookup END,
                   consecutive_timeouts = 0,
                   provider = COALESCE($2, provider),
                   model = COALESCE($3, model),
                   api_endpoint = COALESCE($4, api_endpoint)
               WHERE id = $5""",
            new_encrypted,
            provider,
            model,
            api_endpoint,
            participant_id,
        )

    async def release_ai_slot(
        self,
        participant_id: str,
    ) -> None:
        """Unbind credentials and park the slot so the display_name is reusable.

        Distinct from ``depart_participant``: the row stays, the key is
        nulled (not overwritten with garbage), status flips to 'reset'.
        The dedupe guard treats 'reset' as 'name free', so a facilitator
        can immediately re-add a fresh AI under the same display_name
        without hitting 409.
        """
        await self._execute(
            """UPDATE participants
               SET api_key_encrypted = NULL,
                   auth_token_hash = NULL,
                   auth_token_lookup = NULL,
                   status = 'reset'
               WHERE id = $1""",
            participant_id,
        )

    async def get_all_with_tokens(self) -> list[Participant]:
        """Fetch all participants with token hashes across sessions."""
        rows = await self._fetch_all(
            "SELECT * FROM participants WHERE auth_token_hash IS NOT NULL",
        )
        return [Participant.from_record(r) for r in rows]

    async def approve(self, participant_id: str) -> Participant:
        """Promote a pending participant to full participant."""
        await self._execute(
            "UPDATE participants SET role = 'participant', approved_at = NOW() WHERE id = $1",
            participant_id,
        )
        record = await self._fetch_one(
            "SELECT * FROM participants WHERE id = $1",
            participant_id,
        )
        return Participant.from_record(record)

    async def delete_participant(self, participant_id: str) -> None:
        """Remove a participant record entirely."""
        await self._execute(
            "DELETE FROM participants WHERE id = $1",
            participant_id,
        )

    async def update_auth_token(
        self,
        participant_id: str,
        *,
        new_hash: str | None,
        new_lookup: str | None,
        expires_at: object,
    ) -> None:
        """Replace token hash + lookup, set new expiry, clear IP binding.

        ``new_lookup`` should be the HMAC-SHA256 of the plaintext token
        (compute_token_lookup) for rotations, or None for revoke (so the
        row drops out of the indexed-lookup path entirely). Audit C-02.
        Migration 025: callers must pass ``new_hash=None`` whenever
        ``new_lookup`` is None to satisfy the
        ``ck_participants_lookup_when_hash`` CHECK.
        """
        await self._execute(
            "UPDATE participants"
            " SET auth_token_hash = $1, auth_token_lookup = $2,"
            " token_expires_at = $3, bound_ip = NULL WHERE id = $4",
            new_hash,
            new_lookup,
            expires_at,
            participant_id,
        )

    async def update_bound_ip(
        self,
        participant_id: str,
        ip: str,
    ) -> None:
        """Bind the participant's session to a client IP."""
        await self._execute(
            "UPDATE participants SET bound_ip = $1 WHERE id = $2",
            ip,
            participant_id,
        )

    async def update_role(
        self,
        participant_id: str,
        new_role: str,
    ) -> None:
        """Change a participant's role."""
        await self._execute(
            "UPDATE participants SET role = $1 WHERE id = $2",
            new_role,
            participant_id,
        )

    async def update_budget(
        self,
        participant_id: str,
        *,
        budget_hourly: float | None = None,
        budget_daily: float | None = None,
        max_tokens_per_turn: int | None = None,
    ) -> str:
        """Update a participant's budget limits and output token cap."""
        return await self._execute(
            "UPDATE participants"
            " SET budget_hourly = $1, budget_daily = $2, max_tokens_per_turn = $3"
            " WHERE id = $4",
            budget_hourly,
            budget_daily,
            max_tokens_per_turn,
            participant_id,
        )


_INSERT_PARTICIPANT_SQL = """
    INSERT INTO participants
        (id, session_id, display_name, role, provider, model,
         model_tier, model_family, context_window,
         api_key_encrypted, auth_token_hash, auth_token_lookup, api_endpoint,
         budget_hourly, budget_daily, invited_by, max_tokens_per_turn)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
"""


def _encrypt_api_key(
    api_key: str | None,
    encryption_key: str,
) -> str | None:
    """Encrypt an API key if provided."""
    if api_key is None:
        return None
    return encrypt_value(api_key, key=encryption_key)


def _hash_auth_token(auth_token: str | None) -> str | None:
    """Hash an auth token with bcrypt if provided."""
    if auth_token is None:
        return None
    return bcrypt.hashpw(
        auth_token.encode(),
        bcrypt.gensalt(),
    ).decode()


def _lookup_auth_token(auth_token: str | None) -> str | None:
    """HMAC token-lookup for indexed resolution if provided. Audit C-02."""
    if auth_token is None:
        return None
    return compute_token_lookup(auth_token)
