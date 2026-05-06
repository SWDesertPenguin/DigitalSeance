"""DB-bound integration tests for spec 013 loop wiring (T024 / T026 / T042-T045).

Exercise the post-013-framework integration paths against a real Postgres
test DB:

- ``_enqueue_batched_for_humans`` looks up human participants and enqueues
  per-recipient (013 §FR-001 routing contract).
- The audit-row-before-role-mutation transactional ordering for
  observer_downgrade (contracts/audit-events.md sequencing rule).

Tests skip cleanly when Postgres isn't reachable (conftest sets that gate).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest

import src.auth  # noqa: F401  -- prime auth package against loop.py circular
from src.orchestrator.high_traffic import ObserverDowngradeThresholds
from src.orchestrator.loop import _enqueue_batched_for_humans
from src.orchestrator.observer_downgrade import (
    Downgrade,
    Suppressed,
    downgrade_audit_payload,
    suppressed_audit_payload,
)
from src.repositories.log_repo import LogRepository
from src.repositories.participant_repo import ParticipantRepository


@dataclass
class _FakeMsg:
    """Minimal Message stand-in matching the shape consumed by _enqueue_batched_for_humans."""

    turn_number: int
    speaker_id: str
    speaker_type: str
    content: str
    token_count: int
    created_at: datetime
    summary_epoch: int | None = None


class _CaptureScheduler:
    """Captures enqueue calls without spawning the real flush task."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue(
        self,
        *,
        session_id: str,
        recipient_id: str,
        source_turn_id: str,
        message: dict[str, Any],
    ) -> None:
        self.calls.append(
            {
                "session_id": session_id,
                "recipient_id": recipient_id,
                "source_turn_id": source_turn_id,
                "message": message,
            }
        )


async def _seed_session(pool: asyncpg.Pool, *, name: str = "013 loop integration") -> str:
    """Create a session, return its ID."""
    from src.repositories.session_repo import SessionRepository

    session, _f, _b = await SessionRepository(pool).create_session(
        name,
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    return session.id


async def _add_ai(pool: asyncpg.Pool, session_id: str, encryption_key: str) -> str:
    repo = ParticipantRepository(pool, encryption_key=encryption_key)
    ai, _ = await repo.add_participant(
        session_id=session_id,
        display_name="AI",
        provider="openai",
        model="gpt-4o",
        model_tier="high",
        model_family="gpt",
        context_window=128000,
        api_key="test-api-key",
        auth_token=uuid.uuid4().hex,
        auto_approve=True,
    )
    return ai.id


async def _add_human(pool: asyncpg.Pool, session_id: str, encryption_key: str) -> str:
    repo = ParticipantRepository(pool, encryption_key=encryption_key)
    human, _ = await repo.add_participant(
        session_id=session_id,
        display_name="Human Reviewer",
        provider="human",
        model="human",
        model_tier="low",
        model_family="human",
        context_window=0,
        auth_token=uuid.uuid4().hex,
        auto_approve=True,
    )
    return human.id


async def _seed_session_with_human(pool: asyncpg.Pool, encryption_key: str) -> tuple[str, str, str]:
    """Create a session + AI speaker + human participant. Returns (session_id, ai_id, human_id)."""
    session_id = await _seed_session(pool)
    ai_id = await _add_ai(pool, session_id, encryption_key)
    human_id = await _add_human(pool, session_id, encryption_key)
    return session_id, ai_id, human_id


@pytest.mark.asyncio
async def test_t024_enqueue_routes_only_to_human_participants(
    pool: asyncpg.Pool, encryption_key: str
) -> None:
    """The DB-lookup enqueue helper enqueues per human participant — and skips AI rows."""
    session_id, _ai_id, human_id = await _seed_session_with_human(pool, encryption_key)
    scheduler = _CaptureScheduler()
    msg = _FakeMsg(
        turn_number=7,
        speaker_id="speaker-ai",
        speaker_type="ai",
        content="hello human",
        token_count=42,
        created_at=datetime.now(UTC),
        summary_epoch=None,
    )

    await _enqueue_batched_for_humans(pool, scheduler, session_id, msg, cost_usd=0.01)

    assert len(scheduler.calls) == 1
    call = scheduler.calls[0]
    assert call["session_id"] == session_id
    assert call["recipient_id"] == human_id
    assert call["source_turn_id"] == f"{session_id}:7"
    assert call["message"]["turn_number"] == 7
    assert call["message"]["content"] == "hello human"
    assert call["message"]["speaker_type"] == "ai"


@pytest.mark.asyncio
async def test_t024_enqueue_no_op_when_no_humans(pool: asyncpg.Pool, encryption_key: str) -> None:
    """Sessions without human participants produce zero enqueue calls (FR-001 gate)."""
    session_id = await _seed_session(pool, name="013 ai-only session")
    await _add_ai(pool, session_id, encryption_key)
    scheduler = _CaptureScheduler()
    msg = _FakeMsg(
        turn_number=1,
        speaker_id="speaker-ai",
        speaker_type="ai",
        content="hi",
        token_count=10,
        created_at=datetime.now(UTC),
    )

    await _enqueue_batched_for_humans(pool, scheduler, session_id, msg, cost_usd=None)

    assert scheduler.calls == []


async def _write_downgrade_audit(
    pool: asyncpg.Pool,
    log_repo: LogRepository,
    session_id: str,
    participant: Any,
) -> None:
    """Write the observer_downgrade row using the contract payload helper."""
    payload = downgrade_audit_payload(
        Downgrade(
            participant=participant,
            trigger_threshold="participants",
            observed=5,
            configured=4,
        )
    )
    facilitator_id = await pool.fetchval(
        "SELECT facilitator_id FROM sessions WHERE id = $1", session_id
    )
    await log_repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="observer_downgrade",
        target_id=participant.id,
        previous_value=payload["previous_value"],
        new_value=payload["new_value"],
    )


@pytest.mark.asyncio
async def test_t042_audit_row_writes_before_role_mutation(
    pool: asyncpg.Pool, encryption_key: str
) -> None:
    """Per contracts/audit-events.md sequencing: admin_audit_log row exists for observer_downgrade
    BEFORE the role column flips to observer.
    """
    session_id, _ai_id, human_id = await _seed_session_with_human(pool, encryption_key)
    log_repo = LogRepository(pool)
    p_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    participant = await p_repo.get_participant(human_id)
    assert participant is not None

    await _write_downgrade_audit(pool, log_repo, session_id, participant)

    audit_rows = await pool.fetch(
        "SELECT * FROM admin_audit_log WHERE session_id = $1 AND action = 'observer_downgrade'",
        session_id,
    )
    assert len(audit_rows) == 1
    prev = json.loads(audit_rows[0]["previous_value"])
    assert prev["role"] == "participant"  # captured BEFORE mutation
    new = json.loads(audit_rows[0]["new_value"])
    assert new["role"] == "observer"

    await p_repo.update_role(participant.id, "observer")
    refreshed = await p_repo.get_participant(human_id)
    assert refreshed.role == "observer"


async def _write_suppressed_audit(
    pool: asyncpg.Pool,
    log_repo: LogRepository,
    session_id: str,
    participant: Any,
) -> None:
    """Write the observer_downgrade_suppressed row using the contract payload helper."""
    payload = suppressed_audit_payload(
        Suppressed(
            participant=participant,
            reason="last_human_protection",
            trigger_threshold="participants",
            observed=5,
            configured=4,
        )
    )
    facilitator_id = await pool.fetchval(
        "SELECT facilitator_id FROM sessions WHERE id = $1", session_id
    )
    await log_repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="observer_downgrade_suppressed",
        target_id=participant.id,
        previous_value=payload["previous_value"],
        new_value=payload["new_value"],
    )


@pytest.mark.asyncio
async def test_t042_suppressed_audit_payload_writes_no_role_mutation(
    pool: asyncpg.Pool, encryption_key: str
) -> None:
    """Suppressed decision writes audit row but leaves role unchanged (FR-011)."""
    session_id, ai_id, human_id = await _seed_session_with_human(pool, encryption_key)
    log_repo = LogRepository(pool)
    p_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    participant = await p_repo.get_participant(human_id)
    assert participant is not None

    await _write_suppressed_audit(pool, log_repo, session_id, participant)

    rows = await pool.fetch(
        "SELECT * FROM admin_audit_log WHERE session_id = $1"
        " AND action = 'observer_downgrade_suppressed'",
        session_id,
    )
    assert len(rows) == 1
    new = json.loads(rows[0]["new_value"])
    assert new["reason"] == "last_human_protection"

    # Role unchanged — Suppressed never mutates
    refreshed = await p_repo.get_participant(human_id)
    assert refreshed.role == "participant"

    # Sanity: AI participant role also untouched
    ai_refreshed = await p_repo.get_participant(ai_id)
    assert ai_refreshed.role == "participant"


async def _drive_one_batch(cadence_s: int = 1) -> list[tuple[str, dict[str, Any]]]:
    """Enqueue one message and wait for cadence flush; return broadcast capture."""
    import asyncio

    from src.web_ui.batch_scheduler import BatchScheduler

    capture: list[tuple[str, dict[str, Any]]] = []

    async def _broadcast(session_id: str, event: dict[str, Any]) -> None:
        capture.append((session_id, event))

    scheduler = BatchScheduler(cadence_s=cadence_s, broadcast=_broadcast)
    scheduler.enqueue(
        session_id="s1",
        recipient_id="human-1",
        source_turn_id="t0",
        message={"turn_number": 0, "content": "hi"},
    )
    await asyncio.sleep(cadence_s + 0.2)
    await scheduler.stop()
    return capture


@pytest.mark.asyncio
async def test_t026_batch_emit_logs_open_close_timestamps(caplog: pytest.LogCaptureFixture) -> None:
    """spec 003 §FR-030: per-envelope hold instrumentation surfaces in operator logs."""
    import logging

    with caplog.at_level(logging.INFO, logger="src.web_ui.batch_scheduler"):
        await _drive_one_batch()

    emit_records = [r for r in caplog.records if "batch_envelope_emit" in r.getMessage()]
    assert len(emit_records) == 1
    msg = emit_records[0].getMessage()
    assert "batch_open_ts=" in msg
    assert "batch_close_ts=" in msg
    assert "hold_ms=" in msg


@pytest.mark.asyncio
async def test_t043_loop_evaluator_writes_audit_before_role_mutation(
    pool: asyncpg.Pool, encryption_key: str
) -> None:
    """ConversationLoop._apply_downgrade_decision writes audit then mutates role."""
    from src.orchestrator.loop import ConversationLoop

    session_id, _ai_id, human_id = await _seed_session_with_human(pool, encryption_key)
    loop = ConversationLoop(pool, encryption_key=encryption_key)
    p_repo = ParticipantRepository(pool, encryption_key=encryption_key)
    participant = await p_repo.get_participant(human_id)
    decision = Downgrade(
        participant=participant, trigger_threshold="tpm", observed=42, configured=30
    )

    await loop._apply_downgrade_decision(session_id, decision)

    rows = await pool.fetch(
        "SELECT * FROM admin_audit_log WHERE session_id = $1 AND action = 'observer_downgrade'",
        session_id,
    )
    assert len(rows) == 1
    refreshed = await p_repo.get_participant(human_id)
    assert refreshed.role == "observer"
    assert session_id in loop._last_downgrade_at


@pytest.mark.asyncio
async def test_t043_loop_evaluator_skips_when_config_unset(
    pool: asyncpg.Pool, encryption_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When SACP_OBSERVER_DOWNGRADE_THRESHOLDS unset, evaluator is a no-op (FR-013/SC-005)."""
    from src.orchestrator.loop import ConversationLoop

    monkeypatch.delenv("SACP_HIGH_TRAFFIC_BATCH_CADENCE_S", raising=False)
    monkeypatch.delenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", raising=False)
    monkeypatch.delenv("SACP_OBSERVER_DOWNGRADE_THRESHOLDS", raising=False)
    session_id, _ai_id, _human_id = await _seed_session_with_human(pool, encryption_key)
    loop = ConversationLoop(pool, encryption_key=encryption_key)
    assert loop._high_traffic_config is None

    await loop._maybe_evaluate_observer_downgrade(session_id)

    rows = await pool.fetch("SELECT * FROM admin_audit_log WHERE session_id = $1", session_id)
    assert rows == []


def test_t045_evaluate_downgrade_cost_under_thresholds_budget() -> None:
    """O(participants) evaluate_downgrade returns within turn-prep budget at Phase 3 ceiling (5)."""
    import time

    from src.orchestrator.observer_downgrade import evaluate_downgrade

    @dataclass
    class _P:
        id: str
        role: str = "participant"
        status: str = "active"
        provider: str = "openai"
        model_tier: str = "mid"
        consecutive_timeouts: int = 0
        last_seen: datetime | None = None

    ps = [_P(id=f"p{i}") for i in range(5)]
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30)

    start = time.monotonic()
    for _ in range(1000):
        evaluate_downgrade(participants=ps, current_tpm=35, thresholds=thresholds)
    elapsed_ms = (time.monotonic() - start) * 1000
    # 1000 evals at participants=5 should complete in well under 1s on any hardware
    assert elapsed_ms < 1000, f"O(participants) evaluator ran {elapsed_ms:.1f}ms for 1000x@5"
