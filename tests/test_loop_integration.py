# SPDX-License-Identifier: AGPL-3.0-or-later

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


async def test_execute_turn_populates_per_stage_timings(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Per-stage timings on routing_log are populated end-to-end (US6 / V14).

    Verifies T048: route_ms / assemble_ms / dispatch_ms / persist_ms and
    advisory_lock_wait_ms are all captured on the success-path routing_log
    row. advisory_lock_wait_ms is 0 when the lock is acquired in under 1ms
    (the common case on a lightly loaded CI runner).
    """
    session, _, _, _ = session_with_participant
    loop = _make_loop(pool)
    await loop.execute_turn(session.id)
    routing = await _fetch_routing_log(pool, session.id)
    assert routing is not None
    assert routing["route_ms"] is not None
    assert routing["route_ms"] >= 0
    assert routing["assemble_ms"] is not None
    assert routing["assemble_ms"] >= 0
    assert routing["dispatch_ms"] is not None
    assert routing["dispatch_ms"] >= 0
    assert routing["persist_ms"] is not None
    assert routing["persist_ms"] >= 0
    assert routing["advisory_lock_wait_ms"] is not None
    assert routing["advisory_lock_wait_ms"] >= 0


async def test_execute_turn_populates_security_layer_duration(
    pool: asyncpg.Pool,
    session_with_participant,
    mock_litellm,
):
    """Per-layer security timings on security_events are populated (US6 / 007 §FR-020).

    Verifies T049: when a security layer flags content, the persisted
    security_events row carries a non-NULL layer_duration_ms.
    """
    leaked = "Here is sk-ant-api03-abcdef0123456789012345678901234567890123456789"
    mock_litellm.acompletion.return_value = _build_fake_response(leaked)
    session, _, _, _ = session_with_participant
    loop = _make_loop(pool)
    await loop.execute_turn(session.id)
    events = await _fetch_security_events(pool, session.id)
    assert events, "expected at least one security_events row for the leaked-key payload"
    exfil_rows = [r for r in events if r["layer"] == "exfiltration"]
    assert exfil_rows, "exfiltration layer should have logged a finding"
    assert exfil_rows[0]["layer_duration_ms"] is not None
    assert exfil_rows[0]["layer_duration_ms"] >= 0


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


async def _fetch_security_events(pool: asyncpg.Pool, session_id: str):
    """Fetch all security_events rows for a session in chronological order."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM security_events WHERE session_id = $1 ORDER BY timestamp",
            session_id,
        )


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
            "UPDATE participants SET budget_daily = 0.001 WHERE session_id = $1",
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
            "UPDATE participants SET consecutive_timeouts = 5 WHERE session_id = $1",
            session_id,
        )
