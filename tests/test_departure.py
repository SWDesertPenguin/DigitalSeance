# SPDX-License-Identifier: AGPL-3.0-or-later

"""T037/T040: Participant departure — key overwrite and status tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.repositories.message_repo import MessageRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def session_with_participant(
    pool: asyncpg.Pool,
) -> tuple[str, str, str]:
    """Create session + participant, return (session_id, pid, original_key)."""
    session_repo = SessionRepository(pool)
    session, facilitator, branch = await session_repo.create_session(
        "Departure Test",
        facilitator_display_name="Facilitator",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    participant_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant, _ = await participant_repo.add_participant(
        session_id=session.id,
        display_name="Departing User",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        api_key="sk-original-secret-key",  # noqa: S106
        auth_token="original-token",  # noqa: S106
        auto_approve=True,
    )
    return session.id, participant.id, participant.api_key_encrypted, branch.id


async def test_departure_overwrites_api_key(
    pool: asyncpg.Pool,
    session_with_participant: tuple[str, str, str, str],
) -> None:
    """API key is overwritten (not nulled) on departure."""
    _, pid, original_encrypted, _ = session_with_participant
    repo = ParticipantRepository(pool, encryption_key=TEST_KEY)

    await repo.depart_participant(pid)
    departed = await repo.get_participant(pid)

    assert departed is not None
    assert departed.api_key_encrypted is not None
    assert departed.api_key_encrypted != original_encrypted


async def test_departure_invalidates_auth_token(
    pool: asyncpg.Pool,
    session_with_participant: tuple[str, str, str, str],
) -> None:
    """Auth token hash is invalidated on departure."""
    _, pid, _, _ = session_with_participant
    repo = ParticipantRepository(pool, encryption_key=TEST_KEY)

    await repo.depart_participant(pid)
    departed = await repo.get_participant(pid)

    assert departed.auth_token_hash is None


async def test_departure_sets_offline_status(
    pool: asyncpg.Pool,
    session_with_participant: tuple[str, str, str, str],
) -> None:
    """Status changes to offline on departure."""
    _, pid, _, _ = session_with_participant
    repo = ParticipantRepository(pool, encryption_key=TEST_KEY)

    await repo.depart_participant(pid)
    departed = await repo.get_participant(pid)

    assert departed.status == "offline"


async def test_departure_retains_messages(
    pool: asyncpg.Pool,
    session_with_participant: tuple[str, str, str, str],
) -> None:
    """Messages from departed participant remain in transcript."""
    sid, pid, _, bid = session_with_participant
    msg_repo = MessageRepository(pool)
    participant_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)

    await msg_repo.append_message(
        session_id=sid,
        branch_id=bid,
        speaker_id=pid,
        speaker_type="human",
        content="I was here",
        token_count=5,
        complexity_score="low",
    )

    await participant_repo.depart_participant(pid)

    messages = await msg_repo.get_by_speaker(sid, pid)
    assert len(messages) == 1
    assert messages[0].content == "I was here"
