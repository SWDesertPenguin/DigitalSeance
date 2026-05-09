# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 AI response shaping — filler scorer + per-family profile dispatch.

Phase 2 deliverables (T014 + T016):

  - ``BehavioralProfile`` frozen dataclass + ``BEHAVIORAL_PROFILES`` dict
    keyed by provider family (six families per FR-003). Each profile
    holds the per-family default threshold, the three signal weights
    (defaults 0.5 / 0.3 / 0.2 per FR-002), and the tightened-Tier-4
    retry-delta text. Module-load assertion enforces that the three
    weights sum to 1.0 per FR-002.
  - ``FillerScore`` and ``ShapingDecision`` transient frozen dataclasses
    per data-model.md "Transient (in-memory) entities". These hold the
    aggregate + per-signal breakdown of one evaluation and the per-turn
    record of how the shaping pipeline disposed of one dispatched
    response, respectively. Their fields surface as ``routing_log``
    columns; they are not persisted as standalone entities.

The filler-scorer signal helpers, the aggregator, the per-family
dispatch, the threshold resolver, and the retry orchestrator all land
in Phase 3 (US1). This module currently exposes only the dataclasses
and the registry — importable from any user-story phase task without
pulling in unimplemented behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Hardcoded shaping retry cap per FR-004. Module-level constant so the
# value is greppable and the joint-cap logic in evaluate_and_maybe_retry
# (Phase 3) reads it directly.
SHAPING_RETRY_CAP = 2


# Tightened Tier 4 delta inserted on retry. v1 ships the Direct preset's
# canonical text uniformly across all six families per spec assumption
# (research.md §1: "All six ship with the same retry_delta_text"). The
# field exists per family in BehavioralProfile so a future amendment can
# tune per-family without a schema break.
_DIRECT_PRESET_DELTA = "Reply briefly and directly. No preamble, no restatement, no closing."


@dataclass(frozen=True)
class BehavioralProfile:
    """Per-provider-family filler-scorer configuration.

    Frozen at module load. Looked up via ``profile_for(provider_family)``
    using the participant's existing ``provider_family`` attribute (no
    new env var, no new config surface).

    Fields per data-model.md "BehavioralProfile":

    - ``default_threshold``: per-family default for SACP_FILLER_THRESHOLD
      when the env var is unset. In ``[0.0, 1.0]``. Per research.md §9:
      anthropic and openai default ``0.60`` (verbose-leaning families);
      gemini, groq, ollama, vllm default ``0.55`` (terser baselines).
    - ``hedge_weight`` / ``restatement_weight`` / ``closing_weight``:
      the three signal weights used by ``_aggregate``. Default
      ``0.5 / 0.3 / 0.2`` per FR-002. Module-load assertion below
      enforces that the three weights sum to 1.0.
    - ``retry_delta_text``: tightened Tier 4 delta inserted on each
      shaping retry. v1 ships the Direct preset's text uniformly per
      spec assumption.
    """

    default_threshold: float
    hedge_weight: float
    restatement_weight: float
    closing_weight: float
    retry_delta_text: str


# Six provider families enumerated in FR-003. Anthropic and openai
# default to 0.60 per research.md §9; the other four default to 0.55.
# All six share the default weights and the Direct-preset retry delta.
BEHAVIORAL_PROFILES: dict[str, BehavioralProfile] = {
    "anthropic": BehavioralProfile(
        default_threshold=0.60,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text=_DIRECT_PRESET_DELTA,
    ),
    "openai": BehavioralProfile(
        default_threshold=0.60,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text=_DIRECT_PRESET_DELTA,
    ),
    "gemini": BehavioralProfile(
        default_threshold=0.55,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text=_DIRECT_PRESET_DELTA,
    ),
    "groq": BehavioralProfile(
        default_threshold=0.55,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text=_DIRECT_PRESET_DELTA,
    ),
    "ollama": BehavioralProfile(
        default_threshold=0.55,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text=_DIRECT_PRESET_DELTA,
    ),
    "vllm": BehavioralProfile(
        default_threshold=0.55,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text=_DIRECT_PRESET_DELTA,
    ),
}


# Module-load assertion per FR-002 / contracts/filler-scorer-adapter.md
# "Aggregation": the three weights MUST sum to 1.0 for every entry. Use
# a small epsilon to absorb float imprecision. Fail loudly at import
# time so a misconfigured profile cannot silently skew scoring.
def _assert_weights_sum_to_one() -> None:
    """Validate every BehavioralProfile entry sums weights to 1.0."""
    epsilon = 1e-9
    for family, profile in BEHAVIORAL_PROFILES.items():
        total = profile.hedge_weight + profile.restatement_weight + profile.closing_weight
        if abs(total - 1.0) > epsilon:
            raise AssertionError(
                f"BehavioralProfile['{family}'] weights sum to {total}, expected 1.0 per FR-002"
            )


_assert_weights_sum_to_one()


@dataclass(frozen=True)
class FillerScore:
    """One filler-scorer evaluation's output.

    Pure-function output from ``compute_filler_score``. Not persisted as
    a standalone entity; its fields surface as ``routing_log`` columns
    (``filler_score`` is the aggregate; the per-signal breakdown is
    informational and read from this dataclass at log time).

    All four float fields are in ``[0.0, 1.0]`` by construction.
    """

    aggregate: float
    hedge_signal: float
    restatement_signal: float
    closing_signal: float
    evaluated_at: datetime


@dataclass(frozen=True)
class ShapingDecision:
    """Per-turn record of how the shaping pipeline disposed of one dispatched response.

    Held in memory until logged; not a standalone entity beyond the
    ``routing_log`` row(s) it produces.

    Fields per data-model.md:

    - ``original_score``: filler score of the first dispatched draft.
    - ``retries_fired``: 0, 1, or 2 (bounded by SHAPING_RETRY_CAP).
    - ``retry_scores``: tuple of FillerScore values, length matches
      ``retries_fired``.
    - ``persisted_index``: 0 (original), 1 (first retry), or 2 (second
      retry) — points into ``[original, *retries]``.
    - ``exhausted``: True iff both retries fired and both exceeded
      threshold. Drives ``routing_log.shaping_reason='filler_retry_exhausted'``.
    """

    original_score: FillerScore
    retries_fired: int
    retry_scores: tuple[FillerScore, ...]
    persisted_index: int
    exhausted: bool
