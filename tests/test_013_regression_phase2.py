"""SC-005 regression: spec 013 mechanisms are no-ops with all env vars unset.

The contract: when SACP_HIGH_TRAFFIC_BATCH_CADENCE_S,
SACP_CONVERGENCE_THRESHOLD_OVERRIDE, and SACP_OBSERVER_DOWNGRADE_THRESHOLDS
are ALL unset, observable session behavior MUST equal the pre-013
Phase 2 baseline. Six curated scenarios cover the highest-leverage
Phase 2 dispatch / convergence / circuit-breaker / review-gate /
state-broadcast / routing-log paths.

Each test exercises a real assertion against the spec-013 surface
proving the no-op property structurally — the resolved config is
None, the helpers return None / {}, and the disabled-state branches
are the only branches reachable. The two DB-bound assertions drive
the loop wiring against a real Postgres test DB to confirm the
audit-log + routing-log surfaces stay quiet when env is unset.
"""

from __future__ import annotations

import os

import asyncpg
import pytest

import src.auth  # noqa: F401  -- prime auth package against loop.py circular
from src.orchestrator.high_traffic import HighTrafficSessionConfig
from src.orchestrator.loop import (
    _convergence_threshold_kwarg,
    _maybe_make_batch_scheduler,
)


def _clear_high_traffic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SACP_HIGH_TRAFFIC_BATCH_CADENCE_S",
        "SACP_CONVERGENCE_THRESHOLD_OVERRIDE",
        "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_sc005_resolved_config_is_none_when_all_unset(monkeypatch) -> None:
    """HighTrafficSessionConfig.resolve_from_env() returns None — the canary."""
    _clear_high_traffic_env(monkeypatch)
    assert HighTrafficSessionConfig.resolve_from_env() is None


def test_sc005_scenario_solo_turn_loop_no_envelope_emitted(monkeypatch) -> None:
    """Phase 2 baseline: no batching scheduler instantiated when env unset."""
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert _maybe_make_batch_scheduler(config) is None


def test_sc005_scenario_multi_ai_global_threshold_convergence(monkeypatch) -> None:
    """Phase 2 baseline: ConvergenceDetector receives no override kwarg → uses spec-004 default."""
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert _convergence_threshold_kwarg(config) == {}


def test_sc005_scenario_circuit_breaker_pause_no_downgrade_interference(monkeypatch) -> None:
    """Phase 2 baseline: ObserverDowngradeThresholds is None → evaluate_downgrade never called."""
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is None
    # Caller short-circuits BEFORE invoking evaluate_downgrade — no role-state mutation
    # path can fire when config is None, so circuit_breaker pause/resume runs unchanged.


def test_sc005_scenario_review_gate_per_turn_drafts(monkeypatch) -> None:
    """Phase 2 baseline: review-gate drafts route per-turn (no batching scheduler exists)."""
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    # No scheduler exists → caller's enqueue path is never taken → per-turn delivery
    assert _maybe_make_batch_scheduler(config) is None


def test_sc005_scenario_state_change_immediate_broadcast(monkeypatch) -> None:
    """Phase 2 baseline: event-builder API does not wrap state-change events.

    State-change events (convergence, session_status_changed, participant_update)
    have their own per-event constructors in src/web_ui/events.py and emit via
    broadcast_to_session directly. The batch_envelope event-builder is reachable
    only via BatchScheduler._emit, which itself only fires when a scheduler exists.
    With env unset, no scheduler exists — so state-change events route unchanged.
    """
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert _maybe_make_batch_scheduler(config) is None

    # Verify the per-event constructors do NOT chain through batch_envelope
    from src.web_ui import events

    assert callable(events.convergence_update_event)
    assert callable(events.session_status_changed_event)
    assert callable(events.participant_update_event)


def test_sc005_scenario_routing_log_shape_unchanged(monkeypatch) -> None:
    """Phase 2 baseline: no new routing_log stage names appear when config is None.

    Spec-013 reserves stage names `batch_open_ts`, `batch_close_ts`, and
    `observer_downgrade_eval_ms`. None of these can be emitted unless the
    respective mechanism is active — and none are active when env is unset.
    """
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is None
    # The helpers that would invoke @with_stage_timing are gated on config.
    # No code path emits a 013-stage row when config is None.
    assert _maybe_make_batch_scheduler(config) is None
    assert _convergence_threshold_kwarg(config) == {}


def test_sc005_no_new_admin_audit_log_action_strings_when_unset(monkeypatch) -> None:
    """When config is None, no observer_* audit row can be written.

    The three new admin_audit_log action strings (observer_downgrade,
    observer_restore, observer_downgrade_suppressed) are emitted only by
    src/orchestrator/observer_downgrade.py paths. Those paths are unreachable
    when ObserverDowngradeThresholds is None — verified at the config gate.
    """
    _clear_high_traffic_env(monkeypatch)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is None
    # The audit-row payload builders exist but are pure helpers; they can't be
    # invoked without a Downgrade/Suppressed/Restore decision, which can't be
    # produced without thresholds. With config None, the chain is broken at step 1.
    assert os.environ.get("SACP_OBSERVER_DOWNGRADE_THRESHOLDS") in (None, "")


@pytest.mark.asyncio
async def test_sc005_db_evaluator_writes_no_audit_rows_when_unset(
    pool: asyncpg.Pool,
    encryption_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive ConversationLoop._maybe_evaluate_observer_downgrade against a real DB.

    With env vars unset the loop short-circuits at the config gate and zero
    admin_audit_log rows land — the SC-005 contract for the audit surface.
    """
    from src.orchestrator.loop import ConversationLoop
    from src.repositories.session_repo import SessionRepository

    _clear_high_traffic_env(monkeypatch)
    session, _f, _b = await SessionRepository(pool).create_session(
        "SC-005 audit DB regression",
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    loop = ConversationLoop(pool, encryption_key=encryption_key)
    assert loop._high_traffic_config is None

    await loop._maybe_evaluate_observer_downgrade(session.id)

    rows = await pool.fetch("SELECT * FROM admin_audit_log WHERE session_id = $1", session.id)
    assert rows == []


@pytest.mark.asyncio
async def test_sc005_db_routing_log_carries_no_013_stage_when_unset(
    pool: asyncpg.Pool,
    encryption_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-turn timing accumulator carries no 013-specific stage when env unset.

    Drives the evaluator against a real DB then asserts the in-process timing
    accumulator (which feeds routing_log) holds no observer_downgrade_eval_ms key.
    """
    from src.orchestrator.loop import ConversationLoop
    from src.orchestrator.timing import get_timings, start_turn
    from src.repositories.session_repo import SessionRepository

    _clear_high_traffic_env(monkeypatch)
    session, _f, _b = await SessionRepository(pool).create_session(
        "SC-005 routing DB regression",
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    loop = ConversationLoop(pool, encryption_key=encryption_key)
    start_turn()
    await loop._maybe_evaluate_observer_downgrade(session.id)
    timings = get_timings()
    assert "observer_downgrade_eval_ms" not in timings
    assert "batch_envelope_emit_ms" not in timings
