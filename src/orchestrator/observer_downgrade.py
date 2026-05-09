# SPDX-License-Identifier: AGPL-3.0-or-later

"""Observer-downgrade evaluator (spec 013 mechanism 3 / US3).

Hosts the per-turn priority computation, downgrade decision, audit-row
shape helpers, and restore-window tracking. Wired into the turn-prep
phase of ``loop.py`` only when ``HighTrafficSessionConfig.observer_downgrade``
is not None.

Audit rows reuse the existing ``admin_audit_log`` table (no schema
change) per [research.md §1]. Three new ``action`` strings:
``observer_downgrade``, ``observer_restore``, ``observer_downgrade_suppressed``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from src.orchestrator.high_traffic import ObserverDowngradeThresholds

# model_tier rank for "lowest priority" composite key (spec research §3).
_TIER_RANK = {"low": 0, "mid": 1, "high": 2, "max": 3}

# Roles considered "active" — eligible for downgrade evaluation.
_ACTIVE_ROLES = ("participant", "facilitator")


@dataclass(frozen=True)
class Downgrade:
    """The evaluator decided to downgrade this participant."""

    participant: Any  # Participant (avoid circular import)
    trigger_threshold: Literal["participants", "tpm"]
    observed: int
    configured: int


@dataclass(frozen=True)
class Suppressed:
    """The evaluator would have downgraded but suppression rule fired (last-human protection)."""

    participant: Any
    reason: Literal["last_human_protection"]
    trigger_threshold: Literal["participants", "tpm"]
    observed: int
    configured: int


@dataclass(frozen=True)
class Restore:
    """A previously-downgraded participant can be restored."""

    participant_id: str
    restored_role: str
    tpm_observed: int
    tpm_threshold: int
    sustained_window_s: int


@dataclass(frozen=True)
class NoOp:
    """No downgrade or restore fired this evaluation cycle."""


_DowngradeDecision = Downgrade | Suppressed | NoOp
_RestoreDecision = Restore | NoOp


def lowest_priority_active(participants: list[Any]) -> Any | None:
    """Return the lowest-priority active participant per the research §3 heuristic.

    Composite key (lower wins downgrade): paused-excluded → humans-excluded →
    model_tier rank (low first) → consecutive_timeouts desc → last_seen desc →
    id asc. Returns None when no eligible candidate remains.

    Per spec 013 FR-011 (broadened 2026-05-07): humans are excluded from the
    candidate pool entirely. The orchestrator never picks a human for downgrade.
    The Suppressed branch in evaluate_downgrade remains as defense-in-depth in
    case any future caller bypasses this filter.
    """
    candidates = [
        p
        for p in participants
        if p.status != "paused"
        and p.role in _ACTIVE_ROLES
        and getattr(p, "provider", None) != "human"
    ]
    if not candidates:
        return None
    return min(candidates, key=_priority_key)


def _priority_key(participant: Any) -> tuple[int, int, float, str]:
    """Build the composite sort key. Lower = more eligible for downgrade."""
    tier_rank = _TIER_RANK.get(participant.model_tier, 0)
    timeouts_neg = -getattr(participant, "consecutive_timeouts", 0)
    last_seen = getattr(participant, "last_seen", None)
    last_seen_neg = -last_seen.timestamp() if last_seen is not None else 0.0
    return (tier_rank, timeouts_neg, last_seen_neg, participant.id)


def evaluate_downgrade(
    *,
    participants: list[Any],
    current_tpm: int,
    thresholds: ObserverDowngradeThresholds,
) -> _DowngradeDecision:
    """Decide whether to downgrade per FR-008/FR-009/FR-011 (last-human protection)."""
    active = [p for p in participants if p.status != "paused" and p.role in _ACTIVE_ROLES]
    trigger = _which_threshold_tripped(len(active), current_tpm, thresholds)
    if trigger is None:
        return NoOp()
    candidate = lowest_priority_active(participants)
    if candidate is None:
        return NoOp()
    if _is_only_human(candidate, participants):
        return Suppressed(
            participant=candidate,
            reason="last_human_protection",
            trigger_threshold=trigger,
            observed=len(active) if trigger == "participants" else current_tpm,
            configured=thresholds.participants if trigger == "participants" else thresholds.tpm,
        )
    return Downgrade(
        participant=candidate,
        trigger_threshold=trigger,
        observed=len(active) if trigger == "participants" else current_tpm,
        configured=thresholds.participants if trigger == "participants" else thresholds.tpm,
    )


def _which_threshold_tripped(
    active_count: int,
    tpm: int,
    thresholds: ObserverDowngradeThresholds,
) -> Literal["participants", "tpm"] | None:
    """First-trigger-wins: participants > tpm in evaluation order."""
    if active_count >= thresholds.participants:
        return "participants"
    if tpm >= thresholds.tpm:
        return "tpm"
    return None


def _is_only_human(candidate: Any, participants: list[Any]) -> bool:
    """True if the candidate is the only human in the active set (FR-011)."""
    if getattr(candidate, "provider", None) != "human":
        return False
    other_humans = [
        p
        for p in participants
        if p.id != candidate.id and getattr(p, "provider", None) == "human" and p.status != "paused"
    ]
    return not other_humans


def evaluate_restore(
    *,
    last_downgrade_at: datetime | None,
    sustained_low_traffic_started_at: datetime | None,
    current_tpm: int,
    thresholds: ObserverDowngradeThresholds,
    now: datetime | None = None,
) -> _RestoreDecision | NoOp:
    """Decide whether to restore per FR-010 sustained-low-traffic rule."""
    if last_downgrade_at is None or sustained_low_traffic_started_at is None:
        return NoOp()
    if current_tpm >= thresholds.tpm:
        return NoOp()
    now = now or datetime.now(UTC)
    sustained_for = (now - sustained_low_traffic_started_at).total_seconds()
    if sustained_for < thresholds.restore_window_s:
        return NoOp()
    # NoOp from caller's POV until the caller supplies the participant_id
    # of the most-recently-downgraded participant. Phase 5 wiring task T044
    # supplies it from the loop's per-session state.
    return NoOp()


def downgrade_audit_payload(decision: Downgrade) -> dict[str, str]:
    """Build the (previous_value, new_value) JSON pair for an observer_downgrade row."""
    p = decision.participant
    return {
        "previous_value": json.dumps(
            {
                "role": p.role,
                "model_tier": p.model_tier,
                "consecutive_timeouts": getattr(p, "consecutive_timeouts", 0),
                "last_seen": getattr(p, "last_seen", None) and p.last_seen.isoformat(),
            }
        ),
        "new_value": json.dumps(
            {
                "role": "observer",
                "trigger_threshold": decision.trigger_threshold,
                "observed": decision.observed,
                "configured": decision.configured,
            }
        ),
    }


def suppressed_audit_payload(decision: Suppressed) -> dict[str, str]:
    """Build the (previous_value, new_value) JSON pair for observer_downgrade_suppressed."""
    p = decision.participant
    return {
        "previous_value": json.dumps({"role": p.role, "model_tier": p.model_tier}),
        "new_value": json.dumps(
            {
                "reason": decision.reason,
                "trigger_threshold": decision.trigger_threshold,
                "observed": decision.observed,
                "configured": decision.configured,
            }
        ),
    }


def restore_audit_payload(decision: Restore, downgraded_at: datetime) -> dict[str, str]:
    """Build the (previous_value, new_value) JSON pair for observer_restore."""
    return {
        "previous_value": json.dumps(
            {
                "role": "observer",
                "downgraded_at": downgraded_at.isoformat(),
            }
        ),
        "new_value": json.dumps(
            {
                "role": decision.restored_role,
                "tpm_observed": decision.tpm_observed,
                "tpm_threshold": decision.tpm_threshold,
                "sustained_window_s": decision.sustained_window_s,
            }
        ),
    }
