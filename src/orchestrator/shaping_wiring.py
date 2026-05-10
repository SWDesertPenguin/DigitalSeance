# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 T029: post-dispatch shaping wiring helpers for the loop.

Lives outside ``loop.py`` so the loop module stays under the
standards-lint per-function ceiling and so the master-switch
short-circuit stays a one-line ``if not enabled: return ...`` at the
loop call site.

Wiring contract per spec.md SC-002 + FR-005:

  - ``response_shaping_enabled()`` reads ``SACP_RESPONSE_SHAPING_ENABLED``
    case-insensitively. ``true`` / ``1`` returns ``True``; everything
    else (unset, empty, ``false``, ``0``, garbage) returns ``False``.
    The validator (``validate_response_shaping_enabled``) ensures any
    value present at startup is one of the canonical shapes; the runtime
    read defaults to off on parse failure.
  - ``shape_response`` is the single entry point the loop calls
    post-dispatch. When the master switch is off it returns
    ``(response, None)`` byte-equal to the pre-feature path. When on,
    it scores the response, fires up to ``SHAPING_RETRY_CAP`` retries
    via the supplied dispatch closure, and returns the persisted draft
    plus a ``ShapingMetadata`` snapshot for the routing-log emitter.
  - The ``provider != 'human'`` filter is enforced explicitly per memory
    ``feedback_exclude_humans_from_dispatch`` even though the dispatch
    path is AI-only by construction (router.next_speaker selects AI).
    Recurring SACP bug class — defense in depth at the wiring layer.
  - Stage timings (T032) use ``record_stage`` so multiple retries
    accumulate into a single ``shaping_score_ms`` /
    ``shaping_retry_dispatch_ms`` total for the turn, matching how
    ``dispatch_ms`` aggregates per-attempt today.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.orchestrator.shaping import (
    SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED,
    SHAPING_REASON_FILLER_RETRY,
    SHAPING_REASON_FILLER_RETRY_EXHAUSTED,
    SHAPING_REASON_PIPELINE_ERROR,
    SHAPING_RETRY_CAP,
    BehavioralProfile,
    ShapingDecision,
    evaluate_and_maybe_retry,
    profile_for,
)
from src.orchestrator.timing import record_stage

if TYPE_CHECKING:
    from src.orchestrator.convergence import ConvergenceDetector
    from src.orchestrator.types import ProviderResponse

log = logging.getLogger(__name__)

# Default compound-retry budget for one shaping evaluation. Mirrors
# ``dispatch_with_retry``'s ``max_retries=3`` default per spec 003
# §FR-031. The shaping cap (``SHAPING_RETRY_CAP=2``) is the binding cap
# in the common case; the compound budget binds only when something else
# already consumed a retry slot earlier in the turn (e.g. a network
# rate-limit retry inside ``dispatch_with_retry``).
_COMPOUND_BUDGET_DEFAULT = 3


@dataclass(frozen=True, slots=True)
class ShapingMetadata:
    """Per-turn shaping outcome surfaced to the routing-log emitter.

    All five fields map 1:1 to alembic 013's new ``routing_log`` columns
    per FR-011 + data-model.md "routing_log extension". A ``None`` field
    means the column is left ``NULL`` for that row (e.g.
    ``shaping_retry_delta_text`` is ``None`` when no retry fired;
    ``shaping_reason`` is ``None`` when the original draft passed
    threshold and no retry was needed).
    """

    shaping_score_ms: int | None
    shaping_retry_dispatch_ms: int | None
    filler_score: float | None
    shaping_retry_delta_text: str | None
    shaping_reason: str | None


# ``ShapingMetadata`` shape recorded when the master switch is off OR
# the speaker is human OR the family has no profile entry. Every column
# is ``None`` so the row is byte-equal to a pre-feature row.
_NULL_METADATA = ShapingMetadata(
    shaping_score_ms=None,
    shaping_retry_dispatch_ms=None,
    filler_score=None,
    shaping_retry_delta_text=None,
    shaping_reason=None,
)


def response_shaping_enabled() -> bool:
    """Read ``SACP_RESPONSE_SHAPING_ENABLED`` and return the master-switch state.

    Truthy values: ``'true'`` / ``'1'`` (case-insensitive). Everything
    else is off, including unset, empty, ``'false'``, ``'0'``, and any
    runtime-corrupted value. Validator (T005) ensures startup-time
    correctness; this function survives runtime drift.
    """
    raw = os.environ.get("SACP_RESPONSE_SHAPING_ENABLED")
    if not raw:
        return False
    return raw.strip().lower() in ("true", "1")


def _profile_or_none(model_family: str) -> BehavioralProfile | None:
    """Look up the profile or return ``None`` when no entry exists.

    An unknown family at this point indicates a misconfigured participant.
    Per the fail-closed contract, we degrade to "no shaping for this
    turn" rather than failing the dispatch — the original draft persists
    unchanged with all five shaping columns NULL. Logged as a warning so
    operators can spot the misconfiguration in the routing-log query.
    """
    try:
        return profile_for(model_family)
    except KeyError:
        log.warning(
            "shaping: no BehavioralProfile entry for model_family=%r; "
            "skipping shaping for this turn (original draft persisted)",
            model_family,
        )
        return None


async def shape_response(
    *,
    speaker: object,
    response: ProviderResponse,
    engine: ConvergenceDetector,
    redispatch: Callable[[str], Awaitable[ProviderResponse]],
) -> tuple[ProviderResponse, ShapingMetadata]:
    """Score the response and maybe replace it with a tightened-delta retry.

    Returns ``(possibly_replaced_response, metadata)``. The metadata
    feeds the routing-log emitter; the response replaces
    ``response.content`` for the security-pipeline + persist path.

    Master-switch off, human speaker, missing family profile, or any
    pipeline error all degrade gracefully to ``(response, NULL_METADATA)``
    -- the loop continues and the original draft persists. SC-002
    byte-equal at every off-path.
    """
    if not response_shaping_enabled():
        return response, _NULL_METADATA
    if getattr(speaker, "provider", None) == "human":
        # Memory feedback_exclude_humans_from_dispatch — defense in
        # depth even though the AI dispatch path is human-free.
        return response, _NULL_METADATA
    profile = _profile_or_none(getattr(speaker, "model_family", "") or "")
    if profile is None:
        return response, _NULL_METADATA
    try:
        return await _run_shaping_pipeline(
            response=response,
            profile=profile,
            engine=engine,
            redispatch=redispatch,
        )
    except Exception:
        log.exception("shaping pipeline raised; persisting original draft (fail-closed)")
        return response, _pipeline_error_metadata()


async def _run_shaping_pipeline(
    *,
    response: ProviderResponse,
    profile: BehavioralProfile,
    engine: ConvergenceDetector,
    redispatch: Callable[[str], Awaitable[ProviderResponse]],
) -> tuple[ProviderResponse, ShapingMetadata]:
    """Score, maybe retry, and assemble the metadata. Pipeline-level helper.

    T032: ``compute_filler_score`` (in shaping.py) runs through
    ``@with_stage_timing('shaping_score_ms')`` so multiple evaluations
    within a turn (original + each retry) accumulate into a single
    ``shaping_score_ms`` total. Retry dispatches accumulate into
    ``shaping_retry_dispatch_ms`` via ``_build_text_dispatch``.
    """
    redispatch_state: dict[str, ProviderResponse] = {}
    dispatch_text = _build_text_dispatch(redispatch, redispatch_state)
    persisted_text, decision, _retries_consumed = await evaluate_and_maybe_retry(
        draft_text=response.content,
        profile=profile,
        engine=engine,
        dispatch=dispatch_text,
        compound_budget_remaining=_COMPOUND_BUDGET_DEFAULT,
    )
    final_response = _select_response(response, persisted_text, redispatch_state)
    metadata = _build_metadata(decision=decision, profile=profile)
    return final_response, metadata


def _build_text_dispatch(
    redispatch: Callable[[str], Awaitable[ProviderResponse]],
    state: dict[str, ProviderResponse],
) -> Callable[[str], Awaitable[str]]:
    """Adapt the ProviderResponse-typed redispatch to the str-typed scorer dispatch.

    The shaping orchestrator (in ``shaping.py``) drives a
    ``Callable[[str], Awaitable[str]]`` (delta_text -> retry_text). The
    loop's redispatch callable returns a full ``ProviderResponse`` (we
    need the cost / token counts for the persisted row). This adapter
    bridges the two by stashing each retry's ``ProviderResponse`` keyed
    by its ``content`` so ``_select_response`` can recover the right
    one downstream.
    """

    async def _dispatch(delta_text: str) -> str:
        retry_start = time.monotonic()
        provider_response = await redispatch(delta_text)
        retry_ms = int((time.monotonic() - retry_start) * 1000)
        record_stage("shaping_retry_dispatch_ms", retry_ms)
        state[provider_response.content] = provider_response
        return provider_response.content

    return _dispatch


def _select_response(
    original: ProviderResponse,
    persisted_text: str,
    retry_state: dict[str, ProviderResponse],
) -> ProviderResponse:
    """Pick the original or a retry's ProviderResponse based on which text persisted.

    The original is identity-equal when ``persisted_text == original.content``;
    otherwise the persisted text matches one of the retries by ``content`` key.
    Falls back to the original on the unlikely cache miss (defensive).
    """
    if persisted_text == original.content:
        return original
    return retry_state.get(persisted_text, original)


def _build_metadata(
    *,
    decision: ShapingDecision,
    profile: BehavioralProfile,
) -> ShapingMetadata:
    """Construct ``ShapingMetadata`` from the orchestrator's decision dataclass.

    Pulls per-stage timing accumulators from the timing context (set by
    ``shape_response``'s ``record_stage`` calls) so the metadata fields
    align with the same numbers ``get_timings()`` would surface to the
    routing-log emitter.
    """
    from src.orchestrator.timing import get_timings

    timings = get_timings()
    score_ms = timings.get("shaping_score_ms")
    retry_ms = timings.get("shaping_retry_dispatch_ms")
    persisted_score = _persisted_filler_score(decision)
    delta_text = profile.retry_delta_text if decision.retries_fired > 0 else None
    reason = _classify_reason(decision=decision, profile=profile)
    return ShapingMetadata(
        shaping_score_ms=score_ms,
        shaping_retry_dispatch_ms=retry_ms,
        filler_score=persisted_score,
        shaping_retry_delta_text=delta_text,
        shaping_reason=reason,
    )


def _persisted_filler_score(decision: ShapingDecision) -> float:
    """Aggregate filler score of the persisted draft (original or last retry)."""
    if decision.retry_scores:
        return decision.retry_scores[-1].aggregate
    return decision.original_score.aggregate


def _classify_reason(
    *,
    decision: ShapingDecision,
    profile: BehavioralProfile,
) -> str | None:
    """Map a ``ShapingDecision`` to its ``routing_log.shaping_reason`` value.

    None when the original draft passed threshold (no retry fired). One
    of ``filler_retry`` / ``filler_retry_exhausted`` /
    ``compound_retry_exhausted`` per FR-011 otherwise.

    The compound-budget-binding case (``exhausted=False`` but the loop
    consumed fewer than ``SHAPING_RETRY_CAP`` slots AND the last retry
    was still above threshold) reports ``compound_retry_exhausted`` per
    research.md §4. ``filler_retry`` covers the success path (a retry
    fell below threshold).
    """
    if decision.retries_fired == 0:
        return None
    if decision.exhausted:
        return SHAPING_REASON_FILLER_RETRY_EXHAUSTED
    from src.orchestrator.shaping import threshold_for

    threshold = threshold_for(profile)
    last_score = decision.retry_scores[-1]
    if decision.retries_fired < SHAPING_RETRY_CAP and last_score.aggregate >= threshold:
        return SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED
    return SHAPING_REASON_FILLER_RETRY


def _pipeline_error_metadata() -> ShapingMetadata:
    """Metadata recorded when the pipeline raised — fail-closed path."""
    return ShapingMetadata(
        shaping_score_ms=None,
        shaping_retry_dispatch_ms=None,
        filler_score=None,
        shaping_retry_delta_text=None,
        shaping_reason=SHAPING_REASON_PIPELINE_ERROR,
    )


# Re-export for the loop wiring's callers; keeps the import surface in
# ``loop.py`` to one module (``shaping_wiring``) rather than splitting
# across ``shaping`` + ``shaping_wiring``.
__all__ = (
    "ShapingMetadata",
    "response_shaping_enabled",
    "shape_response",
)
