# SPDX-License-Identifier: AGPL-3.0-or-later

"""US3 acceptance tests: observer-downgrade (spec 013 FR-008-FR-012)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.orchestrator.high_traffic import ObserverDowngradeThresholds
from src.orchestrator.observer_downgrade import (
    Downgrade,
    NoOp,
    Suppressed,
    downgrade_audit_payload,
    evaluate_downgrade,
    evaluate_restore,
    lowest_priority_active,
    suppressed_audit_payload,
)


@dataclass
class _FakeParticipant:
    """Minimal Participant stand-in for evaluator tests."""

    id: str
    role: str = "participant"
    status: str = "active"
    provider: str = "openai"
    model_tier: str = "mid"
    consecutive_timeouts: int = 0
    last_seen: datetime | None = None


def _participants(*specs: tuple[str, str, int]) -> list[Any]:
    """Build a list from (id, model_tier, consecutive_timeouts) tuples."""
    return [_FakeParticipant(id=i, model_tier=tier, consecutive_timeouts=t) for i, tier, t in specs]


def test_us3_priority_heuristic_lowest_tier_wins() -> None:
    """Among ties, the lowest model_tier participant downgrades first."""
    ps = _participants(("a", "high", 0), ("b", "low", 0), ("c", "mid", 0))
    assert lowest_priority_active(ps).id == "b"


def test_us3_priority_heuristic_timeouts_break_tie() -> None:
    """Within a tier, more recent consecutive_timeouts wins."""
    ps = _participants(("a", "mid", 0), ("b", "mid", 3), ("c", "mid", 0))
    assert lowest_priority_active(ps).id == "b"


def test_us3_priority_heuristic_id_ascending_breaks_remaining_tie() -> None:
    """When tier + timeouts identical, lexicographic id-ascending tie-break."""
    ps = _participants(("zebra", "low", 0), ("apple", "low", 0))
    assert lowest_priority_active(ps).id == "apple"


def test_us3_paused_participants_excluded_from_priority_pool() -> None:
    """Paused participants are excluded — they're not active."""
    ps = _participants(("a", "low", 0), ("b", "mid", 0))
    ps[0].status = "paused"
    assert lowest_priority_active(ps).id == "b"


def test_us3_acceptance_1_thresholds_tripped_emits_downgrade() -> None:
    """5-participant + 35 tpm + thresholds participants:4,tpm:30 → downgrade."""
    ps = _participants(*[(f"p{i}", "mid", 0) for i in range(5)])
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30)
    decision = evaluate_downgrade(participants=ps, current_tpm=35, thresholds=thresholds)
    assert isinstance(decision, Downgrade)
    assert decision.trigger_threshold == "participants"
    assert decision.observed == 5
    assert decision.configured == 4


def test_us3_acceptance_3_no_downgrade_when_thresholds_unmet() -> None:
    """3-participant + 10 tpm + thresholds participants:4,tpm:30 → NoOp."""
    ps = _participants(*[(f"p{i}", "mid", 0) for i in range(3)])
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30)
    decision = evaluate_downgrade(participants=ps, current_tpm=10, thresholds=thresholds)
    assert isinstance(decision, NoOp)


def test_us3_lone_human_excluded_from_candidacy_falls_to_ai() -> None:
    """Per FR-011 (broadened 2026-05-07): humans excluded from candidate pool entirely.

    Lone human in session, AIs all at same tier → lowest AI by id-asc tie-break gets
    downgraded. The Suppressed branch is dead-code for this path post-amendment.
    """
    ps = [
        _FakeParticipant(id="a", provider="openai", model_tier="high"),
        _FakeParticipant(id="b", provider="anthropic", model_tier="high"),
        _FakeParticipant(id="c", provider="anthropic", model_tier="high"),
        _FakeParticipant(id="d", provider="anthropic", model_tier="high"),
        _FakeParticipant(id="solo-human", provider="human", model_tier="low"),
    ]
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30)
    decision = evaluate_downgrade(participants=ps, current_tpm=35, thresholds=thresholds)
    assert isinstance(decision, Downgrade)
    assert decision.participant.id == "a"  # lowest id among AIs at same tier
    assert decision.participant.provider != "human"


def test_us3_multiple_humans_all_excluded_falls_to_lowest_ai() -> None:
    """Per FR-011 (broadened): multi-human session also excludes ALL humans.

    Original FR-011 had a "only human" carve-out; amendment broadens to all humans.
    """
    ps = [
        _FakeParticipant(id="a", provider="anthropic", model_tier="high"),
        _FakeParticipant(id="b", provider="anthropic", model_tier="high"),
        _FakeParticipant(id="c", provider="anthropic", model_tier="high"),
        _FakeParticipant(id="human-1", provider="human", model_tier="mid"),
        _FakeParticipant(id="human-2", provider="human", model_tier="low"),
    ]
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30)
    decision = evaluate_downgrade(participants=ps, current_tpm=35, thresholds=thresholds)
    assert isinstance(decision, Downgrade)
    assert decision.participant.provider != "human"
    assert decision.participant.id == "a"  # lowest id among AIs at same tier


def test_us3_humans_never_in_candidate_pool() -> None:
    """Direct contract on lowest_priority_active: humans never returned as candidates."""
    ps = [
        _FakeParticipant(id="ai-1", provider="openai", model_tier="max"),
        _FakeParticipant(id="ai-2", provider="anthropic", model_tier="max"),
        _FakeParticipant(id="human-x", provider="human", model_tier="n/a"),
    ]
    candidate = lowest_priority_active(ps)
    assert candidate is not None
    assert candidate.provider != "human"


def test_us3_all_humans_session_returns_no_candidate() -> None:
    """A pure-human session (no AIs) yields None — evaluator returns NoOp upstream."""
    ps = [
        _FakeParticipant(id="h1", provider="human", model_tier="n/a"),
        _FakeParticipant(id="h2", provider="human", model_tier="n/a"),
    ]
    assert lowest_priority_active(ps) is None
    thresholds = ObserverDowngradeThresholds(participants=2, tpm=30)
    decision = evaluate_downgrade(participants=ps, current_tpm=35, thresholds=thresholds)
    assert isinstance(decision, NoOp)


def test_us3_acceptance_2_restore_window_must_be_sustained() -> None:
    """Restore requires sustained-low-traffic for the full window (FR-010)."""
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30, restore_window_s=120)
    now = datetime.now(UTC)
    # Sustained for only 60s — below 120s window
    decision = evaluate_restore(
        last_downgrade_at=now - timedelta(seconds=300),
        sustained_low_traffic_started_at=now - timedelta(seconds=60),
        current_tpm=10,
        thresholds=thresholds,
        now=now,
    )
    assert isinstance(decision, NoOp)


def test_us3_acceptance_4_restore_blocked_when_tpm_above_threshold() -> None:
    """If current tpm is still above threshold, restore is NoOp regardless of window."""
    thresholds = ObserverDowngradeThresholds(participants=4, tpm=30, restore_window_s=120)
    now = datetime.now(UTC)
    decision = evaluate_restore(
        last_downgrade_at=now - timedelta(seconds=600),
        sustained_low_traffic_started_at=now - timedelta(seconds=600),
        current_tpm=35,
        thresholds=thresholds,
        now=now,
    )
    assert isinstance(decision, NoOp)


def test_us3_audit_payload_downgrade_shape() -> None:
    """downgrade_audit_payload produces the contract-defined JSON shape."""
    p = _FakeParticipant(id="p1", role="participant", model_tier="low", consecutive_timeouts=2)
    decision = Downgrade(participant=p, trigger_threshold="tpm", observed=42, configured=30)
    payload = downgrade_audit_payload(decision)
    assert "previous_value" in payload and "new_value" in payload
    import json

    prev = json.loads(payload["previous_value"])
    new = json.loads(payload["new_value"])
    assert prev == {
        "role": "participant",
        "model_tier": "low",
        "consecutive_timeouts": 2,
        "last_seen": None,
    }
    assert new == {"role": "observer", "trigger_threshold": "tpm", "observed": 42, "configured": 30}


def test_us3_audit_payload_suppressed_shape() -> None:
    """suppressed_audit_payload produces the contract-defined JSON shape."""
    p = _FakeParticipant(id="p1", role="participant", provider="human", model_tier="low")
    decision = Suppressed(
        participant=p,
        reason="last_human_protection",
        trigger_threshold="participants",
        observed=5,
        configured=4,
    )
    payload = suppressed_audit_payload(decision)
    import json

    new = json.loads(payload["new_value"])
    assert new["reason"] == "last_human_protection"
    assert new["trigger_threshold"] == "participants"


def test_us3_acceptance_3_unset_thresholds_means_no_evaluation() -> None:
    """When thresholds env var is unset, ObserverDowngradeThresholds is None — caller skips."""
    import os

    from src.orchestrator.high_traffic import HighTrafficSessionConfig

    # When env unset, resolve_from_env returns None
    for name in (
        "SACP_HIGH_TRAFFIC_BATCH_CADENCE_S",
        "SACP_CONVERGENCE_THRESHOLD_OVERRIDE",
        "SACP_OBSERVER_DOWNGRADE_THRESHOLDS",
    ):
        os.environ.pop(name, None)
    config = HighTrafficSessionConfig.resolve_from_env()
    assert config is None
