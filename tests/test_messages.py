"""US3: Messages recorded immutably — append, query, and immutability tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.repositories.errors import SessionNotActiveError
from src.repositories.message_repo import MessageRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_and_speaker(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Create a session and return (session_id, speaker_id)."""
    repo = SessionRepository(pool)
    session, participant, _ = await repo.create_session(
        "Message Test Session",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id


@pytest.fixture
def repo(pool: asyncpg.Pool) -> MessageRepository:
    """Provide a MessageRepository."""
    return MessageRepository(pool)


async def test_append_assigns_sequential_turn_numbers(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Messages get sequential turn numbers starting from 0."""
    session_id, speaker_id = session_and_speaker

    msg0 = await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="human",
        content="First message",
        token_count=10,
        complexity_score="low",
    )
    msg1 = await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="ai",
        content="Second message",
        token_count=50,
        complexity_score="low",
    )

    assert msg0.turn_number == 0
    assert msg1.turn_number == 1
    assert msg0.branch_id == "main"


async def test_append_persists_all_fields(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """All message fields are persisted correctly."""
    session_id, speaker_id = session_and_speaker

    msg = await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="ai",
        content="Test content here",
        token_count=42,
        complexity_score="high",
        cost_usd=0.003,
        parent_turn=None,
        summary_epoch=1,
    )

    assert msg.content == "Test content here"
    assert msg.token_count == 42
    assert msg.speaker_type == "ai"
    assert msg.complexity_score == "high"
    assert msg.cost_usd == 0.003
    assert msg.summary_epoch == 1


async def test_get_recent_returns_in_turn_order(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """get_recent returns messages in ascending turn order."""
    session_id, speaker_id = session_and_speaker

    for i in range(5):
        await repo.append_message(
            session_id=session_id,
            branch_id="main",
            speaker_id=speaker_id,
            speaker_type="ai",
            content=f"Message {i}",
            token_count=10,
            complexity_score="low",
        )

    recent = await repo.get_recent(session_id, "main", limit=3)
    assert len(recent) == 3
    assert recent[0].turn_number < recent[1].turn_number
    assert recent[1].turn_number < recent[2].turn_number
    assert recent[-1].content == "Message 4"


async def test_multiple_speaker_types(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """Messages with different speaker types persist correctly."""
    session_id, speaker_id = session_and_speaker
    types = ["human", "ai", "system", "summary"]

    for st in types:
        await repo.append_message(
            session_id=session_id,
            branch_id="main",
            speaker_id=speaker_id,
            speaker_type=st,
            content=f"{st} content",
            token_count=10,
            complexity_score="low",
        )

    recent = await repo.get_recent(session_id, "main", limit=4)
    actual_types = [m.speaker_type for m in recent]
    assert actual_types == types


async def test_parent_turn_tree_structure(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """parent_turn enables tree navigation."""
    session_id, speaker_id = session_and_speaker

    msg0 = await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="human",
        content="Root",
        token_count=5,
        complexity_score="low",
    )
    msg1 = await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="ai",
        content="Reply",
        token_count=20,
        complexity_score="low",
        parent_turn=msg0.turn_number,
    )

    assert msg1.parent_turn == 0


async def test_append_rejects_inactive_session(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
    pool: asyncpg.Pool,
) -> None:
    """Appending to a non-active session raises SessionNotActiveError."""
    session_id, speaker_id = session_and_speaker

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET status = 'paused' WHERE id = $1",
            session_id,
        )

    with pytest.raises(SessionNotActiveError):
        await repo.append_message(
            session_id=session_id,
            branch_id="main",
            speaker_id=speaker_id,
            speaker_type="human",
            content="Should fail",
            token_count=5,
            complexity_score="low",
        )


async def test_get_summaries_filters_by_type(
    repo: MessageRepository,
    session_and_speaker: tuple[str, str],
) -> None:
    """get_summaries returns only summary-type messages."""
    session_id, speaker_id = session_and_speaker

    await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="ai",
        content="Regular message",
        token_count=20,
        complexity_score="low",
    )
    await repo.append_message(
        session_id=session_id,
        branch_id="main",
        speaker_id=speaker_id,
        speaker_type="summary",
        content='{"decisions": []}',
        token_count=30,
        complexity_score="low",
        summary_epoch=1,
    )

    summaries = await repo.get_summaries(session_id, "main")
    assert len(summaries) == 1
    assert summaries[0].speaker_type == "summary"
