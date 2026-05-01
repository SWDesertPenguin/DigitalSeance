"""Audit C-02: HMAC-keyed token-lookup index tests.

Pre-fix `_find_by_token` bcrypt-scanned every row in participants where
auth_token_hash IS NOT NULL on every authenticate(). Post-fix it probes
the indexed `auth_token_lookup` column first (HMAC-SHA256 of plaintext)
and falls back to scan only for grandfathered rows whose lookup is
NULL.
"""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.auth.token_lookup import compute_token_lookup
from src.repositories.errors import TokenInvalidError
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_pid(pool: asyncpg.Pool) -> tuple[str, str]:
    """Create a session and return (session_id, facilitator_id)."""
    session_repo = SessionRepository(pool)
    session, _, _ = await session_repo.create_session(
        "Lookup Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, session.facilitator_id


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def _add_with_token(pool: asyncpg.Pool, session_id: str, token: str) -> str:
    """Helper: add a participant carrying `token`; return their id."""
    repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auth_token=token,
        auto_approve=True,
    )
    return participant.id


async def test_add_participant_populates_lookup(
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """add_participant() writes the HMAC alongside the bcrypt hash."""
    sid, _ = session_pid
    pid = await _add_with_token(pool, sid, "lookup-token-add")  # noqa: S106
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_token_lookup FROM participants WHERE id = $1",
            pid,
        )
    assert row is not None
    assert row["auth_token_lookup"] == compute_token_lookup("lookup-token-add")


async def test_authenticate_uses_lookup_path(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """A valid token resolves through the indexed lookup column."""
    sid, _ = session_pid
    pid = await _add_with_token(pool, sid, "lookup-token-auth")  # noqa: S106
    result = await auth.authenticate("lookup-token-auth", "127.0.0.1")
    assert result.id == pid


async def test_authenticate_rejects_wrong_token(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """A token whose HMAC doesn't match any row raises TokenInvalidError."""
    sid, _ = session_pid
    await _add_with_token(pool, sid, "the-real-token")  # noqa: S106
    with pytest.raises(TokenInvalidError):
        await auth.authenticate("not-the-real-token", "127.0.0.1")


async def test_grandfathered_null_lookup_falls_back_to_scan(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """A row with hash but NULL lookup (pre-migration token) still resolves.

    Simulates a participant who joined before migration 009 ran. Their
    auth_token_hash is intact, auth_token_lookup is NULL. _find_by_token
    must fall back to bcrypt-scan and authenticate them.
    """
    sid, _ = session_pid
    pid = await _add_with_token(pool, sid, "grandfathered-token")  # noqa: S106
    # Simulate pre-migration state: NULL out the lookup column.
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET auth_token_lookup = NULL WHERE id = $1",
            pid,
        )
    result = await auth.authenticate("grandfathered-token", "127.0.0.1")
    assert result.id == pid


async def test_rotate_token_populates_new_lookup(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """rotate_token writes a fresh HMAC for the new plaintext."""
    sid, _ = session_pid
    pid = await _add_with_token(pool, sid, "pre-rotation")  # noqa: S106
    new_token = await auth.rotate_token(pid)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_token_lookup FROM participants WHERE id = $1",
            pid,
        )
    assert row is not None
    assert row["auth_token_lookup"] == compute_token_lookup(new_token)
    # Old token must no longer authenticate.
    with pytest.raises(TokenInvalidError):
        await auth.authenticate("pre-rotation", "127.0.0.1")


async def test_revoke_token_nulls_lookup(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """revoke_token clears the lookup column so the row drops out of probes."""
    sid, fid = session_pid
    pid = await _add_with_token(pool, sid, "to-be-revoked")  # noqa: S106
    await auth.revoke_token(
        facilitator_id=fid,
        session_id=sid,
        participant_id=pid,
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT auth_token_lookup FROM participants WHERE id = $1",
            pid,
        )
    assert row is not None
    assert row["auth_token_lookup"] is None
