"""US6: Facilitator transfer tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.auth.service import AuthService
from src.repositories.errors import NotFacilitatorError
from src.repositories.log_repo import LogRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_with_two(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session with facilitator + active participant."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Transfer Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    bob, _ = await p_repo.add_participant(
        session_id=session.id,
        display_name="Bob",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auto_approve=True,
    )
    return session.id, facilitator.id, bob.id


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def test_transfer_updates_roles(
    auth: AuthService,
    session_with_two: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Transfer swaps roles correctly."""
    sid, fid, bob_id = session_with_two
    await auth.transfer_facilitator(
        facilitator_id=fid,
        session_id=sid,
        target_id=bob_id,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    old = await p_repo.get_participant(fid)
    new = await p_repo.get_participant(bob_id)
    assert old.role == "participant"
    assert new.role == "facilitator"


async def test_transfer_updates_session(
    auth: AuthService,
    session_with_two: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Transfer updates session.facilitator_id."""
    sid, fid, bob_id = session_with_two
    await auth.transfer_facilitator(
        facilitator_id=fid,
        session_id=sid,
        target_id=bob_id,
    )
    session_repo = SessionRepository(pool)
    session = await session_repo.get_session(sid)
    assert session.facilitator_id == bob_id


async def test_transfer_logged(
    auth: AuthService,
    session_with_two: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Transfer is logged to admin audit log."""
    sid, fid, bob_id = session_with_two
    await auth.transfer_facilitator(
        facilitator_id=fid,
        session_id=sid,
        target_id=bob_id,
    )
    log_repo = LogRepository(pool)
    entries = await log_repo.get_audit_log(sid)
    actions = [e.action for e in entries]
    assert "transfer_facilitator" in actions


async def _create_session_with_pending(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Helper: create session + pending participant."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Pending Transfer Test",
        facilitator_display_name="Admin",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    pending, _ = await p_repo.add_participant(
        session_id=session.id,
        display_name="Pending",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auto_approve=False,
    )
    return session.id, facilitator.id, pending.id


async def test_transfer_to_pending_rejected(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """Cannot transfer to a pending participant."""
    sid, fid, pid = await _create_session_with_pending(pool)
    with pytest.raises(ValueError, match="participant"):
        await auth.transfer_facilitator(
            facilitator_id=fid,
            session_id=sid,
            target_id=pid,
        )


async def test_non_facilitator_transfer_rejected(
    auth: AuthService,
    session_with_two: tuple[str, str, str],
) -> None:
    """Non-facilitator cannot initiate transfer."""
    sid, fid, bob_id = session_with_two
    with pytest.raises(NotFacilitatorError):
        await auth.transfer_facilitator(
            facilitator_id=bob_id,  # Bob is not facilitator
            session_id=sid,
            target_id=fid,
        )
