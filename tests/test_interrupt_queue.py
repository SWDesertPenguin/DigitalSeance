# SPDX-License-Identifier: AGPL-3.0-or-later

"""US6: Interrupt queue — priority ordering and delivery tracking."""

from __future__ import annotations

import asyncpg
import pytest

from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.session_repo import SessionRepository


@pytest.fixture
async def session_and_speaker(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Create a session and return (session_id, participant_id)."""
    repo = SessionRepository(pool)
    session, participant, _ = await repo.create_session(
        "Interrupt Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id


@pytest.fixture
def repo(pool: asyncpg.Pool) -> InterruptRepository:
    """Provide an InterruptRepository."""
    return InterruptRepository(pool)


async def test_enqueue_creates_pending_entry(
    repo: InterruptRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Enqueued interjections start as pending."""
    sid, pid = session_and_speaker
    entry = await repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="Stop and discuss this",
        priority=1,
    )
    assert entry.status == "pending"
    assert entry.content == "Stop and discuss this"
    assert entry.priority == 1
    assert entry.delivered_at is None


async def test_priority_ordering(
    repo: InterruptRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """High priority interjections come before normal ones."""
    sid, pid = session_and_speaker
    await repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="Normal",
        priority=1,
    )
    await repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="Urgent",
        priority=2,
    )
    pending = await repo.get_pending(sid)
    assert len(pending) == 2
    assert pending[0].content == "Urgent"
    assert pending[1].content == "Normal"


async def test_fifo_within_same_priority(
    repo: InterruptRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Same-priority interjections delivered in creation order."""
    sid, pid = session_and_speaker
    await repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="First",
        priority=1,
    )
    await repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="Second",
        priority=1,
    )
    pending = await repo.get_pending(sid)
    assert pending[0].content == "First"
    assert pending[1].content == "Second"


async def test_mark_delivered(
    repo: InterruptRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Marking delivered updates status and sets timestamp."""
    sid, pid = session_and_speaker
    entry = await repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="Deliver me",
    )
    delivered = await repo.mark_delivered(entry.id)
    assert delivered.status == "delivered"
    assert delivered.delivered_at is not None

    # No longer appears in pending
    pending = await repo.get_pending(sid)
    assert all(p.id != entry.id for p in pending)
