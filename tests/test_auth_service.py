"""US1/US3/US4: Token auth, rotation, and revocation tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.repositories.errors import (
    AuthRequiredError,
    TokenInvalidError,
)
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_with_token(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session + participant with token. Returns (sid, pid, token)."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Auth Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    participant_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant, token = await participant_repo.add_participant(
        session_id=session.id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auth_token="test-token-bob",  # noqa: S106
        auto_approve=True,
    )
    return session.id, participant.id, "test-token-bob"


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def test_valid_token_authenticates(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Valid token returns the correct participant."""
    _, pid, token = session_with_token
    result = await auth.authenticate(token, "127.0.0.1")
    assert result.id == pid


async def test_invalid_token_rejected(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Invalid token raises TokenInvalidError."""
    with pytest.raises(TokenInvalidError):
        await auth.authenticate("wrong-token", "127.0.0.1")


async def test_missing_token_rejected(auth: AuthService) -> None:
    """Missing token raises AuthRequiredError."""
    with pytest.raises(AuthRequiredError):
        await auth.authenticate(None, "127.0.0.1")


async def test_empty_token_rejected(auth: AuthService) -> None:
    """Empty string token raises AuthRequiredError."""
    with pytest.raises(AuthRequiredError):
        await auth.authenticate("", "127.0.0.1")


async def test_rotation_returns_new_token(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Token rotation returns a new plaintext token."""
    _, pid, old_token = session_with_token
    new_token = await auth.rotate_token(pid)
    assert new_token != old_token
    assert len(new_token) > 0


async def test_old_token_rejected_after_rotation(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """Old token fails after rotation."""
    _, pid, old_token = session_with_token
    await auth.rotate_token(pid)
    with pytest.raises(TokenInvalidError):
        await auth.authenticate(old_token, "127.0.0.1")


async def test_new_token_works_after_rotation(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
) -> None:
    """New token authenticates after rotation."""
    _, pid, _ = session_with_token
    new_token = await auth.rotate_token(pid)
    result = await auth.authenticate(new_token, "127.0.0.1")
    assert result.id == pid


async def test_revocation_invalidates_token(
    auth: AuthService,
    session_with_token: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Revoked token is rejected."""
    sid, pid, token = session_with_token
    # Get facilitator ID
    session_repo = SessionRepository(pool)
    session = await session_repo.get_session(sid)
    await auth.revoke_token(
        facilitator_id=session.facilitator_id,
        session_id=sid,
        participant_id=pid,
    )
    with pytest.raises(TokenInvalidError):
        await auth.authenticate(token, "127.0.0.1")
