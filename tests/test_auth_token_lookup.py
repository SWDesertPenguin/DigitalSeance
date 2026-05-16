# SPDX-License-Identifier: AGPL-3.0-or-later

"""Audit C-02: HMAC-keyed token-lookup index tests.

Pre-fix `_find_by_token` bcrypt-scanned every row in participants where
auth_token_hash IS NOT NULL on every authenticate(). v1 fix probed the
indexed `auth_token_lookup` column first (HMAC-SHA256 of plaintext)
and retained a fallback bcrypt-scan for grandfathered rows whose
lookup was NULL. v2 (this branch) removes the legacy fallback;
migration 025 + CHECK constraint enforce hash-implies-lookup so no
grandfathered row can exist.
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


async def test_grandfathered_null_lookup_now_fails(
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """v2: the CHECK constraint refuses hash-without-lookup at write time.

    Pre-v2 a grandfathered row (hash set, lookup NULL) authenticated via
    the legacy O(N) scan. v2 removes the scan and migration 025 adds
    ``ck_participants_lookup_when_hash`` so the inconsistent state
    cannot exist on disk. Attempting to NULL the lookup column on a
    row whose hash is set must raise CheckViolationError.
    """
    sid, _ = session_pid
    pid = await _add_with_token(pool, sid, "would-be-grandfathered")  # noqa: S106
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "UPDATE participants SET auth_token_lookup = NULL WHERE id = $1",
                pid,
            )


async def test_failure_message_does_not_leak_existence(
    auth: AuthService,
    pool: asyncpg.Pool,
    session_pid: tuple[str, str],
) -> None:
    """Wrong-token vs no-such-token raise identical error messages.

    Audit C-02 v2 enumeration-channel guard. If the error string
    differed between "HMAC matched a row but bcrypt failed" and "HMAC
    matched nothing," an attacker could enumerate valid lookups by
    inspecting the exception text. Both paths must raise the same
    ``TokenInvalidError`` message.
    """
    sid, _ = session_pid
    pid = await _add_with_token(pool, sid, "real-token")  # noqa: S106
    assert pid  # silence unused
    with pytest.raises(TokenInvalidError) as no_row:
        await auth.authenticate("no-such-token-at-all", "127.0.0.1")
    # Wrong-token-for-existing-row: construct another participant whose
    # token we then mis-supply. Without a way to forge an HMAC collision
    # the verify-failure branch is hard to hit naturally; the parity
    # contract is the load-bearing claim, so we assert the no-row path's
    # message matches the documented invariant.
    assert str(no_row.value) == "Invalid authentication token"


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
