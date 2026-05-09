# SPDX-License-Identifier: AGPL-3.0-or-later

"""US6: Budget enforcement tests."""

from __future__ import annotations

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.orchestrator.budget import BudgetEnforcer
from src.repositories.log_repo import LogRepository
from src.repositories.participant_repo import ParticipantRepository
from src.repositories.session_repo import SessionRepository

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def participant_with_budget(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Create session + participant with $1 daily budget."""
    session_repo = SessionRepository(pool)
    session, facilitator, _ = await session_repo.create_session(
        "Budget Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    # Set budget via SQL
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET budget_daily = 1.00 WHERE id = $1",
            facilitator.id,
        )
    return session.id, facilitator.id


async def test_within_budget_passes(
    pool: asyncpg.Pool,
    participant_with_budget: tuple[str, str],
) -> None:
    """Participant within budget is allowed."""
    _, pid = participant_with_budget
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant = await p_repo.get_participant(pid)
    enforcer = BudgetEnforcer(LogRepository(pool))
    assert await enforcer.check_budget(participant) is True


async def test_exceeded_budget_fails(
    pool: asyncpg.Pool,
    participant_with_budget: tuple[str, str],
) -> None:
    """Participant over budget is blocked."""
    _, pid = participant_with_budget
    log_repo = LogRepository(pool)
    # Log usage that exceeds the $1 budget
    await log_repo.log_usage(
        participant_id=pid,
        turn_number=0,
        input_tokens=10000,
        output_tokens=5000,
        cost_usd=1.50,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant = await p_repo.get_participant(pid)
    enforcer = BudgetEnforcer(log_repo)
    assert await enforcer.check_budget(participant) is False


async def test_no_budget_always_passes(
    pool: asyncpg.Pool,
) -> None:
    """Participant with no budget set is always allowed."""
    session_repo = SessionRepository(pool)
    _, facilitator, _ = await session_repo.create_session(
        "No Budget Test",
        facilitator_display_name="Bob",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    p_repo = ParticipantRepository(pool, encryption_key=TEST_KEY)
    participant = await p_repo.get_participant(facilitator.id)
    enforcer = BudgetEnforcer(LogRepository(pool))
    assert await enforcer.check_budget(participant) is True
