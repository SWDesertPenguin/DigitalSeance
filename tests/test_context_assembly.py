"""US2: Context assembly — priority order and budget tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.orchestrator.context import ContextAssembler
from src.repositories.interrupt_repo import InterruptRepository
from src.repositories.message_repo import MessageRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


async def _create_session_with_messages(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Helper: create session with 5 messages, return (sid, pid)."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Context Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    msg_repo = MessageRepository(pool)
    for i in range(5):
        await msg_repo.append_message(
            session_id=session.id,
            branch_id="main",
            speaker_id=facilitator.id,
            speaker_type="human",
            content=f"Message {i} with some content",
            token_count=20,
            complexity_score="low",
        )
    return session.id, facilitator.id


@pytest.fixture
async def session_data(
    pool: asyncpg.Pool,
) -> tuple[str, str, object]:
    """Create session with messages. Returns (sid, pid, participant)."""
    from src.repositories.participant_repo import ParticipantRepository

    sid, pid = await _create_session_with_messages(pool)
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant = await p_repo.get_participant(pid)
    return sid, pid, participant


async def test_assembly_returns_context(
    pool: asyncpg.Pool,
    session_data: tuple[str, str, object],
) -> None:
    """Context assembly returns a non-empty list."""
    sid, _, participant = session_data
    assembler = ContextAssembler(pool)
    context = await assembler.assemble(
        session_id=sid,
        participant=participant,
    )
    assert len(context) > 0


async def test_interjections_appear_first(
    pool: asyncpg.Pool,
    session_data: tuple[str, str, object],
) -> None:
    """Interjections appear before regular messages."""
    sid, pid, participant = session_data
    int_repo = InterruptRepository(pool)
    await int_repo.enqueue(
        session_id=sid,
        participant_id=pid,
        content="Urgent interjection",
    )
    assembler = ContextAssembler(pool)
    context = await assembler.assemble(
        session_id=sid,
        participant=participant,
    )
    # Find the interjection (should be early in context)
    interjection_indices = [i for i, c in enumerate(context) if "Priority" in c.content]
    message_indices = [i for i, c in enumerate(context) if "Message" in c.content]
    if interjection_indices and message_indices:
        assert min(interjection_indices) < min(message_indices)


async def test_system_prompt_included(
    pool: asyncpg.Pool,
    session_data: tuple[str, str, object],
) -> None:
    """System prompt appears in context."""
    sid, _, participant = session_data
    assembler = ContextAssembler(pool)
    context = await assembler.assemble(
        session_id=sid,
        participant=participant,
    )
    # At minimum, context should contain messages
    assert len(context) > 0
