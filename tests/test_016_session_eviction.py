# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 016 -- session metric eviction tests.

Covers:
- SC-003: after eviction, session series absent from /metrics
- FR-006: eviction fires within grace window (tested synchronously)
- SC-004: bounded series count after multiple sessions
"""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from src.observability.metrics_registry import (
    evict_session,
    get_registry,
    inc_participant_tokens,
    inc_routing_decision,
    reset_registry_for_tests,
    schedule_session_eviction,
    set_convergence_similarity,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_registry_for_tests()


# ---------------------------------------------------------------------------
# SC-003: evicted session series absent from registry
# ---------------------------------------------------------------------------


def test_sc003_token_series_absent_after_eviction() -> None:
    """After evict_session, token counter series for that session disappear."""
    inc_participant_tokens(
        session_id="s1",
        participant_id="p1",
        prompt_tokens=100,
        completion_tokens=50,
    )
    output_before = generate_latest(get_registry()).decode()
    assert "s1" in output_before

    evict_session("s1")
    output_after = generate_latest(get_registry()).decode()
    assert 'session_id="s1"' not in output_after


def test_sc003_convergence_gauge_absent_after_eviction() -> None:
    """After evict_session, convergence gauge for that session disappears."""
    set_convergence_similarity(session_id="s2", similarity=0.8)
    output_before = generate_latest(get_registry()).decode()
    assert "s2" in output_before

    evict_session("s2")
    output_after = generate_latest(get_registry()).decode()
    assert "s2" not in output_after or "sacp_session_convergence_similarity" not in output_after


def test_sc003_routing_counter_absent_after_eviction() -> None:
    """After evict_session, routing decision counter for that session disappears."""
    inc_routing_decision(session_id="s3", routing_mode="dispatched", skip_reason="")
    output_before = generate_latest(get_registry()).decode()
    assert "s3" in output_before

    evict_session("s3")
    output_after = generate_latest(get_registry()).decode()
    assert 'session_id="s3"' not in output_after


def test_sc003_other_session_survives_eviction() -> None:
    """Evicting session A must not remove session B's series."""
    inc_participant_tokens(
        session_id="sessionA", participant_id="pA", prompt_tokens=10, completion_tokens=5
    )
    inc_participant_tokens(
        session_id="sessionB", participant_id="pB", prompt_tokens=20, completion_tokens=10
    )

    evict_session("sessionA")
    output = generate_latest(get_registry()).decode()
    assert 'session_id="sessionA"' not in output
    assert 'session_id="sessionB"' in output


# ---------------------------------------------------------------------------
# FR-006: eviction fires on schedule_session_eviction (synchronous path)
# ---------------------------------------------------------------------------


def test_fr006_schedule_eviction_no_loop_fires_immediately() -> None:
    """Without a running asyncio loop, schedule_session_eviction evicts synchronously."""
    inc_participant_tokens(
        session_id="sync-evict", participant_id="p1", prompt_tokens=5, completion_tokens=2
    )

    output_before = generate_latest(get_registry()).decode()
    assert "sync-evict" in output_before

    # No running loop -> immediate synchronous eviction
    schedule_session_eviction("sync-evict", grace_s=0)
    output_after = generate_latest(get_registry()).decode()
    assert 'session_id="sync-evict"' not in output_after


# ---------------------------------------------------------------------------
# SC-004: bounded series count after many sessions
# ---------------------------------------------------------------------------


def test_sc004_series_bounded_after_10_sessions() -> None:
    """After creating and evicting 10 sessions, registry only retains active ones."""
    # Create 10 sessions
    for i in range(10):
        sid = f"session-{i}"
        inc_participant_tokens(
            session_id=sid, participant_id=f"p{i}", prompt_tokens=i + 1, completion_tokens=1
        )
        set_convergence_similarity(session_id=sid, similarity=0.5)

    output_before = generate_latest(get_registry()).decode()
    for i in range(10):
        assert f"session-{i}" in output_before

    # Evict all but the last two
    for i in range(8):
        evict_session(f"session-{i}")

    output_after = generate_latest(get_registry()).decode()
    # Evicted sessions must be absent
    for i in range(8):
        assert f'session_id="session-{i}"' not in output_after
    # Remaining sessions must still be present
    assert 'session_id="session-8"' in output_after
    assert 'session_id="session-9"' in output_after


def test_sc004_evict_nonexistent_session_is_safe() -> None:
    """Evicting a session with no registered series must not raise."""
    evict_session("session-never-existed")  # must not raise


# ---------------------------------------------------------------------------
# Eviction tracker isolation
# ---------------------------------------------------------------------------


def test_eviction_tracker_clears_on_reset() -> None:
    """reset_registry_for_tests must also clear the eviction tracker state."""
    inc_participant_tokens(
        session_id="pre-reset", participant_id="p1", prompt_tokens=5, completion_tokens=2
    )
    reset_registry_for_tests()

    # After reset, evicting the previously-tracked session is a no-op (state cleared)
    evict_session("pre-reset")  # must not raise
    output = generate_latest(get_registry()).decode()
    assert "pre-reset" not in output
