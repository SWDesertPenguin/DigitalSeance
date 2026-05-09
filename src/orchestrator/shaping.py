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

Phase 3 (US1) deliverables added below T014 / T016:

  - Three pure signal helpers — ``_hedge_signal``, ``_restatement_signal``,
    ``_closing_signal`` — per contracts/filler-scorer-adapter.md. Each
    returns a float in ``[0.0, 1.0]`` over a candidate draft. These are
    private (underscore-prefixed) because callers consume the aggregate
    via ``compute_filler_score`` (T026) — the per-signal breakdown is
    surfaced through the ``FillerScore`` dataclass for ``routing_log``
    introspection only.

The aggregator, per-family dispatch, threshold resolver, and retry
orchestrator land later in Phase 3 (T026-T028). Until then this module
exposes the dataclasses, the registry, and the three pure signal
helpers — importable from any user-story phase task without pulling in
unimplemented orchestration behavior.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

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
