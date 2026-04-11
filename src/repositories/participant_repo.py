"""Participant repository — join, config, encryption, departure."""

from __future__ import annotations

import uuid

import asyncpg
import bcrypt

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
        auth_token: str | None = None,
        auto_approve: bool = False,
    ) -> tuple[Participant, str | None]:
        """Add a participant, encrypting API key and hashing token."""
        participant_id = uuid.uuid4().hex[:12]
        encrypted_key = _encrypt_api_key(api_key, self._encryption_key)
        token_hash = _hash_auth_token(auth_token)
        role = "participant" if auto_approve else "pending"

        await self._execute(
            _INSERT_PARTICIPANT_SQL,
            participant_id,
            session_id,
            display_name,
            role,
            provider,
            model,
            model_tier,
            model_family,
            context_window,
            encrypted_key,
            token_hash,
        )

        record = await self._fetch_one(
            "SELECT * FROM participants WHERE id = $1",
            participant_id,
        )
        return Participant.from_record(record), auth_token

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
                   status = 'offline'
               WHERE id = $2""",
            overwrite,
            participant_id,
        )


_INSERT_PARTICIPANT_SQL = """
    INSERT INTO participants
        (id, session_id, display_name, role, provider, model,
         model_tier, model_family, context_window,
         api_key_encrypted, auth_token_hash)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
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
