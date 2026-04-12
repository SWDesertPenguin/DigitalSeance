"""US5: Session lifecycle — status transitions and atomic deletion."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.repositories.errors import InvalidTransitionError
from src.repositories.log_repo import LogRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
def repo(pool: asyncpg.Pool) -> SessionRepository:
    """Provide a SessionRepository."""
    return SessionRepository(pool)


async def _create_session(repo: SessionRepository) -> tuple[str, str, str]:
    """Helper: create session, return (session_id, facilitator_id, branch_id)."""
    session, participant, branch = await repo.create_session(
        "Lifecycle Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id, branch.id


async def test_pause_and_resume(repo: SessionRepository) -> None:
    """Active → paused → active transitions work."""
    sid, _, _ = await _create_session(repo)

    paused = await repo.update_status(sid, "paused")
    assert paused.status == "paused"

    resumed = await repo.update_status(sid, "active")
    assert resumed.status == "active"


async def test_archive_from_active(repo: SessionRepository) -> None:
    """Active → archived transition works."""
    sid, _, _ = await _create_session(repo)
    archived = await repo.update_status(sid, "archived")
    assert archived.status == "archived"


async def test_invalid_transition_rejected(
    repo: SessionRepository,
) -> None:
    """Archived → active is not allowed."""
    sid, _, _ = await _create_session(repo)
    await repo.update_status(sid, "archived")
    with pytest.raises(InvalidTransitionError):
        await repo.update_status(sid, "active")


async def test_atomic_deletion_removes_data(
    repo: SessionRepository,
    pool: asyncpg.Pool,
) -> None:
    """Delete removes messages/participants but preserves audit log."""
    sid, pid, bid = await _create_session(repo)
    msg_repo = MessageRepository(pool)
    log_repo = LogRepository(pool)

    await _seed_session_data(msg_repo, log_repo, sid, pid, bid)
    await repo.delete_session(sid)

    assert await repo.get_session(sid) is None
    audit = await log_repo.get_audit_log(sid)
    actions = [e.action for e in audit]
    assert "delete_session" in actions


async def _seed_session_data(
    msg_repo: MessageRepository,
    log_repo: LogRepository,
    sid: str,
    pid: str,
    bid: str,
) -> None:
    """Add a message and audit entry for deletion testing."""
    await msg_repo.append_message(
        session_id=sid,
        branch_id=bid,
        speaker_id=pid,
        speaker_type="human",
        content="Test",
        token_count=5,
        complexity_score="low",
    )
    await log_repo.log_admin_action(
        session_id=sid,
        facilitator_id=pid,
        action="test_action",
        target_id="test",
    )
