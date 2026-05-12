# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 027 standby evaluator unit tests (T015 of tasks.md).

Covers:
  - Each of the four detection signals individually.
  - Precedence chain (paused > standby, circuit_open > standby).
  - Evaluator skip for `wait_mode='always'`.
  - Pivot rate cap.
  - Cycle-count increment on still-standby ticks.

DB-backed; skipped automatically when Postgres is unreachable per the
project conftest pattern.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from src.orchestrator import standby

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pool(_run_migrations: str) -> asyncpg.Pool:
    """Yield a fresh pool for each test, reusing the migrated DB."""
    pool_obj = await asyncpg.create_pool(_run_migrations, min_size=1, max_size=4)
    try:
        yield pool_obj
    finally:
        await pool_obj.close()


async def _seed_session(pool: asyncpg.Pool) -> str:
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES ($1, $2, 'active')",
            session_id,
            "test session",
        )
    return session_id


async def _seed_participant(
    pool: asyncpg.Pool,
    session_id: str,
    *,
    wait_mode: str = "wait_for_human",
    status: str = "active",
    role: str = "participant",
    provider: str = "anthropic",
) -> str:
    pid = f"p_{uuid.uuid4().hex[:10]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO participants (
              id, session_id, display_name, role, provider, model,
              model_tier, model_family, context_window, supports_tools,
              supports_streaming, status, wait_mode
            ) VALUES (
              $1, $2, 'TestP', $3, $4, 'm', 't', 'f', 100, true, true, $5, $6
            )
            """,
            pid,
            session_id,
            role,
            provider,
            status,
            wait_mode,
        )
    return pid


async def test_evaluator_skips_always_mode(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    await _seed_participant(pool, session_id, wait_mode="always")
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert result.entered == []
    assert result.exited == []


async def test_evaluator_skips_circuit_open(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="circuit_open")
    async with pool.acquire() as conn:
        await _insert_pending_question(conn, session_id, pid)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert (pid, "awaiting_human") not in result.entered


async def test_evaluator_skips_paused(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="paused")
    async with pool.acquire() as conn:
        await _insert_pending_question(conn, session_id, pid)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert (pid, "awaiting_human") not in result.entered


async def test_signal_unresolved_question_fires(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id)
    async with pool.acquire() as conn:
        await _insert_pending_question(conn, session_id, pid)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert (pid, "awaiting_human") in result.entered


async def test_signal_pending_review_gate_fires(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id)
    async with pool.acquire() as conn:
        await _insert_pending_review_gate(conn, session_id, pid)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert (pid, "awaiting_gate") in result.entered


async def test_evaluator_excludes_humans(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, provider="human")
    async with pool.acquire() as conn:
        await _insert_pending_question(conn, session_id, pid)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert (pid, "awaiting_human") not in result.entered


async def test_cycle_count_increments_when_still_standby(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="standby")
    async with pool.acquire() as conn:
        await _insert_pending_question(conn, session_id, pid)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert pid in result.cycle_increments
    assert (pid, "awaiting_human") not in result.entered


async def test_already_standby_exits_when_signal_clears(pool: asyncpg.Pool) -> None:
    """A standby participant with NO active signals must exit on the next tick."""
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="standby")
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert pid in result.exited


async def test_always_mode_clears_existing_standby(pool: asyncpg.Pool) -> None:
    """A participant in standby whose wait_mode flips to always must exit."""
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="standby", wait_mode="always")
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert pid in result.exited


async def test_pivot_rate_cap_zero_disables(pool: asyncpg.Pool) -> None:
    """When the rate cap is 0 the pivot evaluator returns no pivot."""
    session_id = await _seed_session(pool)
    config = standby.StandbyConfig(pivot_rate_cap_per_session=0)
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    assert result.pivot_text is None


async def _seed_pivot_eligible(pool: asyncpg.Pool, session_id: str, pid: str) -> None:
    """Helper: backdate the participant's standby_entered audit row by 700s."""
    past_ts = datetime.now(UTC) - timedelta(seconds=700)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE participants SET standby_cycle_count = 10 WHERE id = $1",
            pid,
        )
        await conn.execute(
            """
            INSERT INTO admin_audit_log (
              session_id, facilitator_id, action, target_id, timestamp
            ) VALUES ($1, 'orchestrator', 'standby_entered', $2, $3)
            """,
            session_id,
            pid,
            past_ts,
        )


async def _seed_existing_pivot_row(pool: asyncpg.Pool, session_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO admin_audit_log (
              session_id, facilitator_id, action, target_id, timestamp
            ) VALUES ($1, 'orchestrator', 'pivot_injected', $1, NOW())
            """,
            session_id,
        )


async def test_pivot_fires_when_thresholds_met(pool: asyncpg.Pool) -> None:
    """Drive a participant past N cycles + timeout and verify pivot fires."""
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="standby")
    await _seed_pivot_eligible(pool, session_id, pid)
    config = standby.StandbyConfig(
        filler_detection_turns=5,
        pivot_timeout_seconds=600,
        pivot_rate_cap_per_session=1,
    )
    result = await standby.evaluate_tick(pool, session_id, current_turn=11, config=config)
    assert result.pivot_text is not None
    assert pid in result.observer_marked


async def test_pivot_skips_when_rate_cap_exhausted(pool: asyncpg.Pool) -> None:
    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id, status="standby")
    await _seed_existing_pivot_row(pool, session_id)
    await _seed_pivot_eligible(pool, session_id, pid)
    config = standby.StandbyConfig(pivot_rate_cap_per_session=1)
    result = await standby.evaluate_tick(pool, session_id, current_turn=11, config=config)
    assert result.pivot_text is None
    assert result.pivot_skipped_rate_cap is True


async def test_apply_eval_result_transitions_to_standby(pool: asyncpg.Pool) -> None:
    from src.repositories.log_repo import LogRepository

    session_id = await _seed_session(pool)
    pid = await _seed_participant(pool, session_id)
    async with pool.acquire() as conn:
        await _insert_pending_question(conn, session_id, pid)
    log_repo = LogRepository(pool)
    config = standby.StandbyConfig()
    result = await standby.evaluate_tick(pool, session_id, current_turn=1, config=config)
    await standby.apply_eval_result(pool, session_id, 1, result, log_repo)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM participants WHERE id = $1", pid)
    assert row["status"] == "standby"


async def _insert_pending_question(
    conn: asyncpg.Connection,
    session_id: str,
    participant_id: str,
) -> None:
    """Insert a detection_events row representing an unresolved question."""
    try:
        await conn.execute(
            """
            INSERT INTO detection_events (
              session_id, participant_id, event_class, disposition,
              trigger_snippet, detector_score, timestamp
            ) VALUES ($1, $2, 'ai_question_opened', 'pending', 'q?', 0.9, NOW())
            """,
            session_id,
            participant_id,
        )
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        pytest.skip("detection_events table not present in this schema")


async def _insert_pending_review_gate(
    conn: asyncpg.Connection,
    session_id: str,
    participant_id: str,
) -> None:
    """Insert a review_gate_drafts row representing a pending gate."""
    try:
        await conn.execute(
            """
            INSERT INTO review_gate_drafts (
              id, session_id, participant_id, turn_number,
              draft_content, status, created_at
            ) VALUES (
              $1, $2, $3, 1, 'draft', 'pending', NOW()
            )
            """,
            f"d_{uuid.uuid4().hex[:8]}",
            session_id,
            participant_id,
        )
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        pytest.skip("review_gate_drafts table not present in this schema")
