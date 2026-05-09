# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 AI response shaping -- filler scorer + per-family profile dispatch.

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

Phase 3 (US1) deliverables (T023-T028):

  - Three pure signal helpers -- ``_hedge_signal``, ``_restatement_signal``,
    ``_closing_signal`` -- per contracts/filler-scorer-adapter.md. Each
    returns a float in ``[0.0, 1.0]`` over a candidate draft.
  - ``_aggregate`` + ``compute_filler_score`` (T026): weighted sum of the
    three signal helpers using the per-family ``BehavioralProfile``
    weights; returns a ``FillerScore`` with the aggregate and per-signal
    breakdown.
  - ``profile_for`` + ``threshold_for`` (T027): per-family profile lookup
    and threshold resolution. ``SACP_FILLER_THRESHOLD`` env var, when set,
    overrides every family's profile default uniformly per research.md
    Sec 9.
  - ``evaluate_and_maybe_retry`` (T028): retry orchestrator. Hardcoded
    ``SHAPING_RETRY_CAP=2`` per FR-004; joint cap with the participant's
    compound-retry budget per FR-006. Pure-orchestrator -- the dispatch
    callable is supplied by the loop wiring (T029) so this module stays
    decoupled from ``loop.py``.

The post-dispatch wiring into ``loop.py`` lands in T029 (next batch).
Until then this module exposes the dataclasses, the registry, the three
pure signal helpers, the aggregator, the per-family dispatch, the
threshold resolver, and the retry orchestrator -- importable from any
user-story phase task.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.orchestrator.timing import with_stage_timing

if TYPE_CHECKING:
    from src.orchestrator.convergence import ConvergenceDetector

log = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Phase 3 (US1): three pure signal helpers
# ---------------------------------------------------------------------------
#
# Each helper returns a float in ``[0.0, 1.0]`` over a candidate draft.
# The helpers are pure — no DB writes, no I/O beyond the embedding read
# in ``_restatement_signal`` (which goes to the convergence engine's
# in-memory ring buffer, not the database). Module-level constants are
# loaded once at import.

# Hardcoded hedge-token list per research.md §3. Lowercased, multi-word
# entries match as substrings against the lowercased draft. Operators
# tune the list via amendment when family-specific patterns surface.
_HEDGE_TOKENS: tuple[str, ...] = (
    "i think",
    "i believe",
    "perhaps",
    "maybe",
    "it seems",
    "it appears",
    "in my opinion",
    "from my perspective",
    "arguably",
    "presumably",
    "i would say",
    "i'd argue",
    "to some extent",
    "more or less",
    "kind of",
    "sort of",
    "in a sense",
    "if i may",
)

# Hardcoded closing-pattern regexes per research.md §3. Each pattern is
# a precompiled re.Pattern so per-call cost is the match-only path, not
# a recompile. Cap of 3 matches keeps a saturation event from masking
# the other two signals (research.md §3 rationale).
_CLOSING_PATTERN_SOURCES: tuple[str, ...] = (
    r"\bhope (this|that) helps\b",
    r"\blet me know if\b",
    r"\bplease (feel free|don'?t hesitate)\b",
    r"\b(best|kind) regards\b",
    r"\bcheers!?\s*$",
    r"\bin (summary|conclusion)[,:]?\s",
    r"\bto (summarize|conclude|wrap up)[,:]?\s",
)
_CLOSING_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(src, re.IGNORECASE | re.MULTILINE) for src in _CLOSING_PATTERN_SOURCES
)
_CLOSING_CAP = 3


def _hedge_signal(draft_text: str) -> float:
    """Hedge-to-content ratio for one draft.

    Per contracts/filler-scorer-adapter.md "Hedge-to-content ratio":

    - Lowercases the draft and counts case-insensitive substring matches
      of every entry in ``_HEDGE_TOKENS``.
    - Denominator is the whitespace-split token count of the draft (no
      tokenizer load — keeps this signal under V14's 50ms scorer budget).
    - Empty draft (zero tokens) returns ``0.0`` per contract.
    - Result is in ``[0.0, 1.0]`` by construction (the count is bounded
      above by the token count in any realistic draft; we cap at ``1.0``
      defensively to absorb pathological inputs without violating the
      aggregator's invariants).
    """
    tokens = draft_text.split()
    if not tokens:
        return 0.0
    lowered = draft_text.lower()
    hedge_count = 0
    for hedge in _HEDGE_TOKENS:
        # Multi-word hedges count once per occurrence; single-word entries
        # collapse to substring matches as well, which is the spec
        # behavior (research.md §3: "case-insensitive match").
        start = 0
        while True:
            idx = lowered.find(hedge, start)
            if idx == -1:
                break
            hedge_count += 1
            start = idx + len(hedge)
    ratio = hedge_count / len(tokens)
    return min(ratio, 1.0)


def _closing_signal(draft_text: str) -> float:
    """Boilerplate closing-pattern match count, capped at 3.

    Per contracts/filler-scorer-adapter.md "Boilerplate closing detection":

    - Counts regex matches across all entries in ``_CLOSING_PATTERNS``.
    - Each pattern contributes the number of distinct, non-overlapping
      matches it finds (``len(re.findall(...))``).
    - Returns ``min(matches, _CLOSING_CAP) / _CLOSING_CAP``; in
      ``[0.0, 1.0]`` by construction.
    - The cap prevents a draft with multiple stacked sign-offs from
      saturating the whole aggregate — leaves headroom for the other
      two signals to contribute (research.md §3 rationale).
    """
    if not draft_text:
        return 0.0
    total = 0
    for pattern in _CLOSING_PATTERNS:
        total += len(pattern.findall(draft_text))
        if total >= _CLOSING_CAP:
            return 1.0
    return total / _CLOSING_CAP


def _max_cosine(candidate_bytes: bytes, recent: list[bytes]) -> float:
    """Max cosine similarity between candidate and any recent embedding.

    Helper extracted from ``_restatement_signal`` so the public helper
    stays under the 25-line standards-lint ceiling. ``candidate_bytes``
    and each ``recent`` entry are float32 byte buffers from the
    sentence-transformers encoder; the cosine math runs in numpy.
    Clamps to ``[0.0, 1.0]`` defensively — cosine of normalized vectors
    is mathematically in that range but float rounding can drift.
    """
    import numpy as np

    from src.orchestrator.convergence import _cosine_sim

    candidate_vec = np.frombuffer(candidate_bytes, dtype=np.float32)
    best = 0.0
    for entry_bytes in recent:
        other_vec = np.frombuffer(entry_bytes, dtype=np.float32)
        sim = _cosine_sim(candidate_vec, other_vec)
        if sim > best:
            best = sim
    return min(max(best, 0.0), 1.0)


async def _restatement_signal(
    draft_text: str,
    engine: ConvergenceDetector,
) -> float:
    """Max cosine similarity vs the prior 1-3 turns' embeddings.

    Per contracts/filler-scorer-adapter.md "Restatement (cosine similarity
    vs prior 1-3 turns)". Reads ``engine.recent_embeddings(depth=3)``;
    no DB hit (FR-012). Reuses spec 004's encoder so no second
    sentence-transformers model loads. Empty buffer / unavailable model
    / embed failure all degrade to ``0.0`` (with warning for the latter
    two) per the fail-closed contract.
    """
    if not draft_text:
        return 0.0
    recent = engine.recent_embeddings(depth=3)
    if not recent:
        return 0.0
    model = getattr(engine, "_model", None)
    if model is None:
        log.warning("Embedding model unavailable; restatement signal degrades to 0.0")
        return 0.0
    from src.orchestrator.convergence import _compute_embedding_async

    try:
        candidate_bytes = await _compute_embedding_async(model, draft_text)
    except Exception:
        log.warning(
            "Embedding pipeline raised; restatement signal degrades to 0.0",
            exc_info=True,
        )
        return 0.0
    return _max_cosine(candidate_bytes, recent)


# ---------------------------------------------------------------------------
# Phase 3 (US1): aggregator + scorer entry point (T026)
# ---------------------------------------------------------------------------


def _aggregate(
    *,
    hedge: float,
    restatement: float,
    closing: float,
    profile: BehavioralProfile,
) -> float:
    """Weighted sum of the three signal floats using per-family weights.

    Per contracts/filler-scorer-adapter.md "Aggregation". Each input is
    in ``[0.0, 1.0]`` and the three weights sum to ``1.0`` per FR-002
    (module-load asserted on every ``BehavioralProfile`` entry), so the
    output is in ``[0.0, 1.0]`` by construction. Defensive clamp absorbs
    float rounding drift at the boundary.
    """
    total = (
        profile.hedge_weight * hedge
        + profile.restatement_weight * restatement
        + profile.closing_weight * closing
    )
    return min(max(total, 0.0), 1.0)


@with_stage_timing("shaping_score_ms")
async def compute_filler_score(
    *,
    draft_text: str,
    profile: BehavioralProfile,
    engine: ConvergenceDetector,
) -> FillerScore:
    """Score a candidate draft on three filler signals.

    Pure function over the draft -- no DB writes, no side effects.
    Reads the engine's in-memory recent-embeddings ring buffer for the
    restatement signal (no DB read per FR-012). Returns a ``FillerScore``
    holding the aggregate and per-signal breakdown; the aggregate
    surfaces as ``routing_log.filler_score`` and the per-signal floats
    are informational for post-hoc audit.

    Per contracts/filler-scorer-adapter.md the three signal helpers do
    not call each other -- the aggregator collects each helper's float
    independently and applies the per-family weighted sum.

    T032 V14 instrumentation: each invocation accumulates into the
    turn's ``shaping_score_ms`` counter via the ``@with_stage_timing``
    decorator. ``record_stage`` is a no-op when no turn context is
    active so unit tests that call this directly don't need a
    ``start_turn()`` boundary.
    """
    hedge = _hedge_signal(draft_text)
    restatement = await _restatement_signal(draft_text, engine)
    closing = _closing_signal(draft_text)
    aggregate = _aggregate(
        hedge=hedge,
        restatement=restatement,
        closing=closing,
        profile=profile,
    )
    return FillerScore(
        aggregate=aggregate,
        hedge_signal=hedge,
        restatement_signal=restatement,
        closing_signal=closing,
        evaluated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Phase 3 (US1): per-family dispatch + threshold resolver (T027)
# ---------------------------------------------------------------------------


def profile_for(provider_family: str) -> BehavioralProfile:
    """Look up the per-family ``BehavioralProfile``.

    Per contracts/filler-scorer-adapter.md "Per-family BehavioralProfile
    dispatch". Family lookup uses the participant's existing
    ``model_family`` attribute -- no new env var, no new config surface.
    Raises ``KeyError`` for unknown families: an unknown family at this
    point indicates a misconfigured participant, not a graceful-degrade
    case (fail loud).
    """
    return BEHAVIORAL_PROFILES[provider_family]


def threshold_for(profile: BehavioralProfile) -> float:
    """Resolve the effective filler-score threshold.

    Per contracts/filler-scorer-adapter.md "Threshold resolution":

    - When ``SACP_FILLER_THRESHOLD`` env var is set, that value overrides
      every family's default uniformly per research.md Sec 9.
    - When unset (or empty / whitespace), each family's
      ``profile.default_threshold`` applies.

    The validator ``validate_filler_threshold`` (T003) ensures any set
    value is a float in ``[0.0, 1.0]`` at startup, so this resolver
    trusts the env-var contents to parse cleanly. Any parse failure here
    falls back to the per-family default with a warning -- runtime
    drift after startup is the only path that lands here.
    """
    raw = os.environ.get("SACP_FILLER_THRESHOLD")
    if raw is None or raw.strip() == "":
        return profile.default_threshold
    try:
        return float(raw)
    except ValueError:
        log.warning(
            "SACP_FILLER_THRESHOLD=%r failed to parse at runtime; "
            "falling back to per-family default %.3f",
            raw,
            profile.default_threshold,
        )
        return profile.default_threshold


# ---------------------------------------------------------------------------
# Phase 3 (US1): retry orchestrator (T028)
# ---------------------------------------------------------------------------
#
# ``evaluate_and_maybe_retry`` is the public entry point that ``loop.py``
# (T029) wires in post-dispatch when ``SACP_RESPONSE_SHAPING_ENABLED=true``.
# It scores the original draft, fires up to ``SHAPING_RETRY_CAP=2`` retries
# with the profile's tightened delta when the score crosses threshold, and
# stops at whichever cap fires first per FR-006:
#
#   - hard cap of 2 retries (FR-004), OR
#   - the participant's compound-retry budget reaching zero (FR-006).
#
# The dispatch callable is supplied by the caller (loop.py) as a closure
# that already has the participant + tier + tightened-delta wiring in
# place. This module owns the orchestration; the loop owns the wiring.

# Reason strings persisted to ``routing_log.shaping_reason`` per FR-011 +
# data-model.md "routing_log extension". Module-level constants so the
# strings are greppable and the loop wiring (T029) reads them directly.
SHAPING_REASON_FILLER_RETRY = "filler_retry"
SHAPING_REASON_FILLER_RETRY_EXHAUSTED = "filler_retry_exhausted"
SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED = "compound_retry_exhausted"
SHAPING_REASON_PIPELINE_ERROR = "shaping_pipeline_error"


async def evaluate_and_maybe_retry(
    *,
    draft_text: str,
    profile: BehavioralProfile,
    engine: ConvergenceDetector,
    dispatch: Callable[[str], Awaitable[str]],
    compound_budget_remaining: int,
) -> tuple[str, ShapingDecision, int]:
    """Score the draft; if over threshold, fire bounded tightened-delta retries.

    Per contracts/filler-scorer-adapter.md "Retry orchestration" and
    research.md Sec 4.

    Joint cap (FR-006): shaping stops at whichever fires first --
    ``SHAPING_RETRY_CAP=2`` (FR-004) OR ``compound_budget_remaining``
    reaching zero. When the compound budget is the binding cap (i.e.
    fewer than 2 slots remain at entry, OR the budget runs out mid-loop
    while ``SHAPING_RETRY_CAP`` would still allow another retry), the
    decision's ``exhausted`` flag stays ``False`` and the caller logs
    ``SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED`` instead of
    ``SHAPING_REASON_FILLER_RETRY_EXHAUSTED``.

    Returns ``(persisted_text, decision, retries_consumed)``. The caller
    persists ``persisted_text`` as the turn's message content (FR-016
    byte-equal: shaping does NOT mutate provider output beyond
    selecting which dispatched draft becomes the persisted one), feeds
    ``decision`` to the routing-log emitter, and decrements its
    compound-retry budget by ``retries_consumed``.
    """
    threshold = threshold_for(profile)
    original_score = await compute_filler_score(
        draft_text=draft_text,
        profile=profile,
        engine=engine,
    )
    if original_score.aggregate < threshold:
        return draft_text, _decision_no_retry(original_score), 0
    persisted_text, retry_scores, exhausted = await _drive_retry_loop(
        original_text=draft_text,
        original_score=original_score,
        threshold=threshold,
        profile=profile,
        engine=engine,
        dispatch=dispatch,
        compound_budget_remaining=compound_budget_remaining,
    )
    decision = ShapingDecision(
        original_score=original_score,
        retries_fired=len(retry_scores),
        retry_scores=tuple(retry_scores),
        persisted_index=_persisted_index(retry_scores, exhausted, threshold),
        exhausted=exhausted,
    )
    return persisted_text, decision, len(retry_scores)


def _decision_no_retry(original_score: FillerScore) -> ShapingDecision:
    """Build a ``ShapingDecision`` for the no-retry path (score below threshold)."""
    return ShapingDecision(
        original_score=original_score,
        retries_fired=0,
        retry_scores=(),
        persisted_index=0,
        exhausted=False,
    )


async def _drive_retry_loop(
    *,
    original_text: str,
    original_score: FillerScore,
    threshold: float,
    profile: BehavioralProfile,
    engine: ConvergenceDetector,
    dispatch: Callable[[str], Awaitable[str]],
    compound_budget_remaining: int,
) -> tuple[str, list[FillerScore], bool]:
    """Run up to SHAPING_RETRY_CAP retries; return (persisted_text, scores, exhausted).

    ``exhausted`` is True iff every retry slot allowed by the joint cap
    was consumed AND the final retry's score was still above threshold.
    The compound-budget-binding case (cap not reached, but budget ran
    out) returns ``exhausted=False`` so the caller logs
    ``compound_retry_exhausted`` rather than ``filler_retry_exhausted``.
    """
    persisted_text = original_text
    persisted_score = original_score
    retry_scores: list[FillerScore] = []
    max_retries = min(SHAPING_RETRY_CAP, max(compound_budget_remaining, 0))
    for _ in range(max_retries):
        retry_text = await dispatch(profile.retry_delta_text)
        retry_score = await compute_filler_score(
            draft_text=retry_text,
            profile=profile,
            engine=engine,
        )
        retry_scores.append(retry_score)
        persisted_text = retry_text
        persisted_score = retry_score
        if retry_score.aggregate < threshold:
            return persisted_text, retry_scores, False
    exhausted = max_retries == SHAPING_RETRY_CAP and persisted_score.aggregate >= threshold
    return persisted_text, retry_scores, exhausted


def _persisted_index(
    retry_scores: list[FillerScore],
    exhausted: bool,
    threshold: float,
) -> int:
    """Index into ``[original, *retry_scores]`` for the persisted draft.

    - 0 retries fired -> 0 (original persisted; only reached when the
      caller bypasses ``_drive_retry_loop`` entirely, but the helper is
      defensive against that path too).
    - Last retry below threshold -> index of that retry (1 or 2).
    - All retries above threshold (exhausted OR compound-budget cap) ->
      index of the last retry fired.
    """
    if not retry_scores:
        return 0
    last = retry_scores[-1]
    if not exhausted and last.aggregate < threshold:
        return len(retry_scores)
    return len(retry_scores)
