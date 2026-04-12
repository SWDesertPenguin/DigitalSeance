"""US7: Token expiry enforcement tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.repositories.errors import TokenExpiredError
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_with_token(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session + participant with token."""
    session_repo = SessionRepository(pool)
    session, _, _ = await session_repo.create_session(
        "Expiry Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant, _ = await p_repo.add_participant(
        session_id=session.id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auth_token="expiry-test-token",  # noqa: S106
        auto_approve=True,
    )
    return session.id, participant.id, "expiry-test-token"


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def test_non_expired_token_works(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Token without expiry authenticates normally."""
    _, pid, token = session_with_token
    result = await auth.authenticate(token, "127.0.0.1")
    assert result.id == pid


async def test_expired_token_rejected(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Expired token raises TokenExpiredError."""
    _, pid, token = session_with_token
    # Set expiry to the past
    past = datetime.utcnow() - timedelta(hours=1)  # noqa: DTZ003
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants" " SET token_expires_at = $1 WHERE id = $2",
            past,
            pid,
        )
    with pytest.raises(TokenExpiredError):
        await auth.authenticate(token, "127.0.0.1")


async def test_rotation_resets_expiry(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Token rotation resets expiry to configured period."""
    _, pid, _ = session_with_token
    await auth.rotate_token(pid)
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    p = await p_repo.get_participant(pid)
    assert p.token_expires_at is not None
    # Should be ~30 days from now
    expected = datetime.now(tz=UTC) + timedelta(days=29)
    expires = p.token_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    assert expires > expected
