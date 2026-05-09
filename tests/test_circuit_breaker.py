# SPDX-License-Identifier: AGPL-3.0-or-later

"""US7: Circuit breaker — auto-pause after consecutive failures."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.orchestrator.circuit_breaker import CircuitBreaker
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def participant_id(pool: asyncpg.Pool) -> str:
    """Create a session and return the facilitator's ID."""
    repo = SessionRepository(pool)
    _, facilitator, _ = await repo.create_session(
        "Breaker Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return facilitator.id


async def test_three_failures_opens_circuit(
    pool: asyncpg.Pool,
    participant_id: str,
) -> None:
    """3 consecutive failures auto-pauses participant."""
    breaker = CircuitBreaker(pool, threshold=3)
    await breaker.record_failure(participant_id)
    await breaker.record_failure(participant_id)
    opened = await breaker.record_failure(participant_id)
    assert opened is True
    assert await breaker.is_open(participant_id) is True

    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    p = await p_repo.get_participant(participant_id)
    assert p.status == "paused"


async def test_success_resets_counter(
    pool: asyncpg.Pool,
    participant_id: str,
) -> None:
    """Success after failures resets counter."""
    breaker = CircuitBreaker(pool, threshold=3)
    await breaker.record_failure(participant_id)
    await breaker.record_failure(participant_id)
    await breaker.record_success(participant_id)
    assert await breaker.is_open(participant_id) is False


async def test_below_threshold_stays_closed(
    pool: asyncpg.Pool,
    participant_id: str,
) -> None:
    """Failures below threshold don't open circuit."""
    breaker = CircuitBreaker(pool, threshold=3)
    opened = await breaker.record_failure(participant_id)
    assert opened is False
    assert await breaker.is_open(participant_id) is False
