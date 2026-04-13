"""Integration tests for ConversationLoop.execute_turn()."""

from __future__ import annotations

import asyncpg

from src.orchestrator.loop import ConversationLoop
from src.repositories.interrupt_repo import InterruptRepository
from tests.conftest import TEST_ENCRYPTION_KEY, _build_fake_response


def _make_loop(pool: asyncpg.Pool) -> ConversationLoop:
    """Create a ConversationLoop with the test encryption key."""
    return ConversationLoop(pool, encryption_key=TEST_ENCRYPTION_KEY)


async def test_execute_turn_persists_message(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Turn execution persists AI response to messages table."""
    session, _, participant, branch = session_with_participant
    loop = _make_loop(pool)
    result = await loop.execute_turn(session.id)
    assert not result.skipped
    row = await _fetch_message(pool, session.id)
    assert row is not None
    assert row["content"] == "Test AI response"


async def test_execute_turn_logs_routing_and_usage(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Turn execution creates routing_log and usage_log entries."""
    session, _, _, _ = session_with_participant
    loop = _make_loop(pool)
    await loop.execute_turn(session.id)
    routing = await _fetch_routing_log(pool, session.id)
    assert routing is not None
    usage = await _fetch_usage_log(pool)
    assert usage is not None
    assert usage["input_tokens"] == 100


async def test_interrupt_delivery(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Pending interrupts are marked delivered after turn."""
    session, facilitator, _, _ = session_with_participant
    int_repo = InterruptRepository(pool)
    entry = await int_repo.enqueue(
        session_id=session.id,
        participant_id=facilitator.id,
        content="Human says hello",
        priority=1,
    )
    loop = _make_loop(pool)
    await loop.execute_turn(session.id)
    row = await _fetch_interrupt(pool, entry.id)
    assert row["delivered_at"] is not None


async def test_budget_exceeded_skips(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Over-budget participants are skipped without dispatch."""
    session, _, _, _ = session_with_participant
    await _set_budget_and_spend_all(pool, session.id)
    loop = _make_loop(pool)
    result = await loop.execute_turn(session.id)
    assert result.skipped
    assert result.skip_reason == "budget_exceeded"
    mock_litellm.acompletion.assert_not_awaited()


async def test_circuit_breaker_skips(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Open circuit breaker skips the participant."""
    session, _, _, _ = session_with_participant
    await _trip_breaker_all(pool, session.id)
    loop = _make_loop(pool)
    result = await loop.execute_turn(session.id)
    assert result.skipped
    assert result.skip_reason == "circuit_open"


async def test_exfiltration_cleaned(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Exfiltration filter redacts secrets before persistence."""
    leaked = "Here is sk-ant-api03-abcdef0123456789012345678901234567890123456789"
    mock_litellm.acompletion.return_value = _build_fake_response(leaked)
    loop = _make_loop(pool)
    session, _, _, _ = session_with_participant
    await loop.execute_turn(session.id)
    row = await _fetch_message(pool, session.id)
    assert "sk-ant-" not in row["content"]


# --- Helpers (under 25 lines each) ---


async def _fetch_message(pool: asyncpg.Pool, session_id: str):
    """Fetch the first message for a session."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM messages WHERE session_id = $1",
            session_id,
        )


async def _fetch_routing_log(pool: asyncpg.Pool, session_id: str):
    """Fetch the first routing log entry for a session."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM routing_log WHERE session_id = $1",
            session_id,
        )


async def _fetch_usage_log(pool: asyncpg.Pool):
    """Fetch the first usage log entry."""
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM usage_log LIMIT 1")


async def _fetch_interrupt(pool: asyncpg.Pool, intr_id: int):
    """Fetch an interrupt queue entry by ID."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM interrupt_queue WHERE id = $1",
            intr_id,
        )


async def _set_budget_and_spend_all(
    pool: asyncpg.Pool,
    session_id: str,
) -> None:
    """Set tiny budget on all participants and seed usage over it."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET budget_daily = 0.001" " WHERE session_id = $1",
            session_id,
        )
        ids = await conn.fetch(
            "SELECT id FROM participants WHERE session_id = $1",
            session_id,
        )
        for row in ids:
            await _seed_usage(conn, row["id"])


async def _seed_usage(conn, participant_id: str) -> None:
    """Insert a usage log entry that exceeds budget."""
    await conn.execute(
        "INSERT INTO usage_log"
        " (participant_id, turn_number, input_tokens,"
        "  output_tokens, cost_usd)"
        " VALUES ($1, 0, 100, 50, 1.0)",
        participant_id,
    )


async def _trip_breaker_all(
    pool: asyncpg.Pool,
    session_id: str,
) -> None:
    """Set consecutive_timeouts above threshold for all participants."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET consecutive_timeouts = 5" " WHERE session_id = $1",
            session_id,
        )
