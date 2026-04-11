"""US7: Review gate drafts — staging lifecycle tests."""

from __future__ import annotations

import asyncpg
import pytest

from src.repositories.review_gate_repo import ReviewGateRepository
from src.repositories.session_repo import SessionRepository


@pytest.fixture
async def session_and_speaker(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Create a session and return (session_id, participant_id)."""
    repo = SessionRepository(pool)
    session, participant, _ = await repo.create_session(
        "Review Gate Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id


@pytest.fixture
def repo(pool: asyncpg.Pool) -> ReviewGateRepository:
    """Provide a ReviewGateRepository."""
    return ReviewGateRepository(pool)


async def test_create_draft_pending(
    repo: ReviewGateRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Created drafts start as pending."""
    sid, pid = session_and_speaker
    draft = await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=0,
        draft_content="AI response text",
        context_summary="Responding to user question",
    )
    assert draft.status == "pending"
    assert draft.draft_content == "AI response text"
    assert draft.resolved_at is None


async def test_approve_draft(
    repo: ReviewGateRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Approving a draft sets status and resolved_at."""
    sid, pid = session_and_speaker
    draft = await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=0,
        draft_content="Good response",
        context_summary="Context",
    )
    resolved = await repo.resolve(draft.id, resolution="approved")
    assert resolved.status == "approved"
    assert resolved.resolved_at is not None


async def test_edit_draft(
    repo: ReviewGateRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Editing stores the edited content separately."""
    sid, pid = session_and_speaker
    draft = await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=0,
        draft_content="Original",
        context_summary="Context",
    )
    resolved = await repo.resolve(
        draft.id,
        resolution="edited",
        edited_content="Improved version",
    )
    assert resolved.status == "edited"
    assert resolved.edited_content == "Improved version"
    assert resolved.draft_content == "Original"


async def test_reject_draft(
    repo: ReviewGateRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Rejecting a draft prevents it from entering the transcript."""
    sid, pid = session_and_speaker
    draft = await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=0,
        draft_content="Bad response",
        context_summary="Context",
    )
    resolved = await repo.resolve(draft.id, resolution="rejected")
    assert resolved.status == "rejected"
    assert resolved.resolved_at is not None


async def test_timeout_draft(
    repo: ReviewGateRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Timed-out drafts auto-resolve."""
    sid, pid = session_and_speaker
    draft = await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=0,
        draft_content="Slow review",
        context_summary="Context",
    )
    resolved = await repo.resolve(draft.id, resolution="timed_out")
    assert resolved.status == "timed_out"


async def test_get_pending_filters_resolved(
    repo: ReviewGateRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """get_pending only returns unresolved drafts."""
    sid, pid = session_and_speaker
    d1 = await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=0,
        draft_content="Resolved",
        context_summary="Context",
    )
    await repo.create_draft(
        session_id=sid,
        participant_id=pid,
        turn_number=1,
        draft_content="Still pending",
        context_summary="Context",
    )
    await repo.resolve(d1.id, resolution="approved")

    pending = await repo.get_pending(sid)
    assert len(pending) == 1
    assert pending[0].draft_content == "Still pending"
