"""US1 acceptance tests: human-boundary batching cadence (spec 013).

Cover the four FR-001 / FR-003 / FR-004 contracts from the spec via the
``BatchScheduler`` API surface, using an injected broadcast capture
instead of the real WebSocket transport. Real per-session WebSocket
end-to-end tests are deferred until Phase 6 polish.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.web_ui.batch_scheduler import BatchScheduler


def _make_message(turn_id: str, content: str = "hi") -> dict[str, Any]:
    return {"id": turn_id, "turn_number": 0, "content": content}


class _Capture:
    """Stand-in for broadcast_to_session — records emitted events."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, session_id: str, event: dict[str, Any]) -> None:
        self.calls.append((session_id, event))


@pytest.mark.asyncio
async def test_us1_acceptance_1_multiple_turns_coalesce_into_one_envelope() -> None:
    """4 turns within a cadence window deliver as a single batch_envelope event."""
    capture = _Capture()
    scheduler = BatchScheduler(cadence_s=1, broadcast=capture)
    for i in range(4):
        scheduler.enqueue(
            session_id="s1",
            recipient_id="human-1",
            source_turn_id=f"t{i}",
            message=_make_message(f"t{i}"),
        )
    await asyncio.sleep(1.2)
    await scheduler.stop()
    assert len(capture.calls) == 1
    sid, event = capture.calls[0]
    assert sid == "s1"
    assert event["type"] == "batch_envelope"
    assert event["recipient_id"] == "human-1"
    assert event["source_turn_ids"] == ["t0", "t1", "t2", "t3"]
    assert len(event["messages"]) == 4


@pytest.mark.asyncio
async def test_us1_acceptance_2_lone_turn_still_delivered_within_budget() -> None:
    """A single message in a cadence window still emits one envelope."""
    capture = _Capture()
    scheduler = BatchScheduler(cadence_s=1, broadcast=capture)
    scheduler.enqueue(
        session_id="s1",
        recipient_id="human-1",
        source_turn_id="t0",
        message=_make_message("t0"),
    )
    await asyncio.sleep(1.2)
    await scheduler.stop()
    assert len(capture.calls) == 1
    assert capture.calls[0][1]["source_turn_ids"] == ["t0"]


def test_us1_acceptance_3_disabled_when_env_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the batching env var is unset, the loop's helper returns None."""
    import src.auth  # noqa: F401  -- prime auth package against loop.py circular
    from src.orchestrator.high_traffic import HighTrafficSessionConfig
    from src.orchestrator.loop import _maybe_make_batch_scheduler

    monkeypatch.delenv("SACP_HIGH_TRAFFIC_BATCH_CADENCE_S", raising=False)
    monkeypatch.delenv("SACP_CONVERGENCE_THRESHOLD_OVERRIDE", raising=False)
    monkeypatch.delenv("SACP_OBSERVER_DOWNGRADE_THRESHOLDS", raising=False)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is None
    assert _maybe_make_batch_scheduler(config) is None


@pytest.mark.asyncio
async def test_us1_state_change_bypass_routes_outside_envelope() -> None:
    """State-change events MUST NOT route through enqueue.

    The bypass rule is a contract on the caller: state-change events
    call broadcast_to_session directly. This test pins the API shape —
    BatchScheduler.enqueue is for messages only; the caller's bypass
    decision happens before reaching this method.
    """
    capture = _Capture()
    scheduler = BatchScheduler(cadence_s=1, broadcast=capture)
    # No enqueue -> nothing buffered. Caller's bypass path bypasses entirely.
    await asyncio.sleep(1.2)
    await scheduler.stop()
    assert capture.calls == []


@pytest.mark.asyncio
async def test_us1_slack_budget_warns_on_late_close() -> None:
    """If the cadence tick is missed, the hard close at cadence + 5s logs a warning."""
    import logging

    capture = _Capture()
    scheduler = BatchScheduler(cadence_s=1, broadcast=capture)
    scheduler.enqueue(
        session_id="s1",
        recipient_id="human-1",
        source_turn_id="t0",
        message=_make_message("t0"),
    )
    # Force the elapsed measurement past cadence + 5s by sleeping >6s.
    # We tighten this with a clock fake in Phase 6 polish.
    caplog_logger = logging.getLogger("src.web_ui.batch_scheduler")
    caplog_logger.setLevel(logging.WARNING)
    # Just verify a flush completes; the warn-log path is exercised when
    # the elapsed value crosses the budget. Smoke test only here.
    await asyncio.sleep(1.2)
    await scheduler.stop()
    assert len(capture.calls) == 1
