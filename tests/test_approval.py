"""US2/US5: Approval flow and facilitator-initiated removal tests."""

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
async def session_with_pending(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session + pending participant. Returns (sid, fid, pid)."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Approval Test",
        facilitator_display_name="Facilitator",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    pending, _ = await p_repo.add_participant(
        session_id=session.id,
        display_name="Pending User",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auto_approve=False,
    )
    return session.id, facilitator.id, pending.id


@pytest.fixture
def auth(pool: asyncpg.Pool) -> AuthService:
    """Provide an AuthService."""
    return AuthService(pool, encryption_key=TEST_KEY)


async def test_approve_changes_role(
    auth: AuthService,
    session_with_pending: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Approval changes role to participant and sets approved_at."""
    sid, fid, pid = session_with_pending
    result = await auth.approve_participant(
        facilitator_id=fid,
        session_id=sid,
        participant_id=pid,
    )
    assert result.role == "participant"
    assert result.approved_at is not None


async def test_approve_logs_to_audit(
    auth: AuthService,
    session_with_pending: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Approval is logged to admin audit log."""
    sid, fid, pid = session_with_pending
    await auth.approve_participant(
        facilitator_id=fid,
        session_id=sid,
        participant_id=pid,
    )
    log_repo = LogRepository(pool)
    entries = await log_repo.get_audit_log(sid)
    actions = [e.action for e in entries]
    assert "approve_participant" in actions


async def test_reject_removes_record(
    auth: AuthService,
    session_with_pending: tuple[str, str, str],
    pool: asyncpg.Pool,
) -> None:
    """Rejection removes the participant record."""
    sid, fid, pid = session_with_pending
    await auth.reject_participant(
        facilitator_id=fid,
        session_id=sid,
        participant_id=pid,
        reason="Not needed",
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    result = await p_repo.get_participant(pid)
    assert result is None


async def test_non_facilitator_approve_rejected(
    auth: AuthService,
    session_with_pending: tuple[str, str, str],
) -> None:
    """Non-facilitator cannot approve participants."""
    sid, _, pid = session_with_pending
    with pytest.raises(NotFacilitatorError):
        await auth.approve_participant(
            facilitator_id=pid,  # pending user trying to approve
            session_id=sid,
            participant_id=pid,
        )


async def _create_removal_session(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Helper: create session + approved participant for removal tests."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Removal Test",
        facilitator_display_name="Admin",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    target, _ = await p_repo.add_participant(
        session_id=session.id,
        display_name="Target",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        auto_approve=True,
    )
    return session.id, facilitator.id, target.id


async def test_remove_triggers_departure(
    auth: AuthService,
    pool: asyncpg.Pool,
) -> None:
    """Removal triggers departure logic and logs to audit."""
    sid, fid, tid = await _create_removal_session(pool)
    await auth.remove_participant(
        facilitator_id=fid,
        session_id=sid,
        participant_id=tid,
        reason="Disruptive behavior",
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    removed = await p_repo.get_participant(tid)
    assert removed.status == "offline"

    log_repo = LogRepository(pool)
    entries = await log_repo.get_audit_log(sid)
    actions = [e.action for e in entries]
    assert "remove_participant" in actions


async def test_self_removal_rejected(
    auth: AuthService,
    session_with_pending: tuple[str, str, str],
) -> None:
    """Facilitator cannot remove themselves."""
    sid, fid, _ = session_with_pending
    with pytest.raises(ValueError, match="yourself"):
        await auth.remove_participant(
            facilitator_id=fid,
            session_id=sid,
            participant_id=fid,
        )
