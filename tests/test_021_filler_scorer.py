# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 Phase 3 (US1) acceptance scenarios T018-T022.

Exercises the full post-dispatch shaping pipeline through the
``shape_response`` wiring helper -- the same entry point ``loop.py``
(T029) calls. Each test maps 1:1 to a scenario in
[spec.md User Story 1 "Acceptance Scenarios"](../specs/021-ai-response-shaping/spec.md):

  - T018 -> Scenario 1: over-threshold draft fires a tightened retry;
    only the persisted draft would enter the transcript (verified via
    the returned ``ProviderResponse`` byte-equality).
  - T019 -> Scenario 2: below-threshold draft -> no retry; original
    response identity-preserved.
  - T020 -> Scenario 3: master switch off -> NULL metadata on every
    field AND user-facing response is byte-equal to a pre-feature run.
    DISTINCT from T017's architectural canary (which asserts no shaping
    code path fires); T020 is the row-introspection canary -- the new
    ``routing_log`` columns carry no shaping-on values.
  - T021 -> Scenario 4 (covers SC-003): both retries exceed threshold
    -> second retry persisted; ``shaping_reason='filler_retry_exhausted'``;
    no infinite loop.
  - T022 -> Scenario 5 (covers SC-006): a retry firing yields a metadata
    record with non-None score / delta-text / per-stage timings and the
    persisted ``filler_score`` reflects the post-retry score, not the
    pre-retry one.

These scenarios use the same minimal duck-type stubs as
``tests/test_021_shaping_wiring.py``: a ``_StubResponse`` for
``ProviderResponse``, a ``_StubSpeaker`` for the participant, and a
``_StubEngine`` for ``ConvergenceDetector`` (empty ring buffer / no
model -> restatement signal degrades to 0.0, which keeps the aggregate
score driven by hedge + closing signals only and lets us pick draft
texts that deterministically cross or stay below threshold).
"""

from __future__ import annotations

import dataclasses

import pytest

import src.auth  # noqa: F401  # prime auth package against loop.py circular
from src.api_bridge.adapter import ProviderResponse
from src.orchestrator import shaping as shaping_module
from src.orchestrator import timing as timing_module
from src.orchestrator.shaping_wiring import (
    ShapingMetadata,
    shape_response,
)

# ---------------------------------------------------------------------------
# Test stubs -- minimal duck types, mirror tests/test_021_shaping_wiring.py
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _StubSpeaker:
    """Minimal stand-in for a Participant.

    Carries only the two attributes ``shape_response`` reads:
    ``provider`` (for the human-filter defense per memory
    ``feedback_exclude_humans_from_dispatch``) and ``model_family``
    (for ``profile_for`` lookup).
    """

    provider: str = "ai"
    model_family: str = "anthropic"


class _StubEngine:
    """ConvergenceDetector stand-in with empty ring buffer + no model.

    The restatement signal degrades to 0.0 under both conditions per
    the fail-closed contract (``contracts/filler-scorer-adapter.md``).
    With restatement zeroed, the aggregate is driven by hedge + closing
    only (weights 0.5 + 0.2 = 0.7 of the total), so test drafts can be
    crafted to deterministically cross or stay below any threshold.
    """

    def recent_embeddings(self, depth: int = 3) -> list[bytes]:
        return []

    @property
    def last_embedding(self) -> bytes | None:
        return None

    _model = None


def _make_response(content: str) -> ProviderResponse:
    """Build a real ``ProviderResponse`` so byte-equality assertions are real."""
    return ProviderResponse(
        content=content,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        model="stub-model",
        latency_ms=42,
    )


async def _drive_shape_response(
    *,
    original_content: str,
    redispatch,
) -> tuple[ProviderResponse, ShapingMetadata]:
    """Helper: build the original response and call ``shape_response``.

    Centralizes the speaker / engine stub plumbing so each scenario test
    stays under the 25-line standards-lint ceiling and reads as
    setup-then-assertions only.
    """
    return await shape_response(
        speaker=_StubSpeaker(),
        response=_make_response(original_content),
        engine=_StubEngine(),
        redispatch=redispatch,
    )


# Hedge-heavy draft tuned to score above any threshold <= ~0.5 with the
# default profile weights (hedge 0.5, restatement 0.3, closing 0.2) and
# the stub engine zeroing restatement. Six hedge tokens over ~16 words
# -> hedge ratio ~0.375; one closing match -> closing 1/3 ~0.333.
# Aggregate: 0.5*0.375 + 0.3*0.0 + 0.2*0.333 = ~0.254. We use a low test
# threshold (0.10) to make the over-threshold case unambiguous.
_HEDGE_HEAVY = (
    "I think perhaps maybe it seems the bridge collapsed. "
    "I believe it appears arguably three workers were injured. "
    "Hope this helps."
)

# Direct draft -- no hedges, no closing markers. Hedge 0.0 + closing 0.0
# -> aggregate 0.0 regardless of threshold.
_DIRECT = "The bridge collapsed at 3 PM. Three workers were injured."


# ---------------------------------------------------------------------------
# Test fixtures -- shaping ON with a low threshold (over-threshold cases)
# ---------------------------------------------------------------------------


@pytest.fixture
def shaping_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Master switch ON; threshold low enough that hedge-heavy drafts cross."""
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "true")
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "0.10")


@pytest.fixture
def shaping_on_high_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Master switch ON; threshold high enough that no draft crosses (no retry)."""
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "true")
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "0.99")


@pytest.fixture
def shaping_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Master switch unset (off). Threshold env state irrelevant under off-mode."""
    monkeypatch.delenv("SACP_RESPONSE_SHAPING_ENABLED", raising=False)


@pytest.fixture(autouse=True)
def _reset_timings() -> None:
    """Each scenario starts with a fresh per-turn timing accumulator.

    ``shape_response`` records into the timing context via
    ``record_stage`` and reads back via ``get_timings`` when assembling
    metadata. Without ``start_turn()`` the recordings are no-ops (per
    ``timing.record_stage`` contract) and metadata timing fields land
    at ``None``. ``start_turn`` here lets T022 assert non-None per-stage
    timings; non-timing-focused scenarios still pass because the timing
    fields are not part of their assertions.
    """
    timing_module.start_turn()
    yield
    timing_module.reset()


# ---------------------------------------------------------------------------
# T018 -- Acceptance scenario 1: over-threshold -> tightened retry fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t018_over_threshold_fires_retry_and_persists_retry_draft(
    shaping_on: None,
) -> None:
    """T018 / Scenario 1 + FR-001 / FR-004 / FR-016.

    Given an over-threshold hedge-heavy draft AND a redispatch closure
    that returns a clean draft below threshold, the wiring fires exactly
    one retry, returns the retry's ``ProviderResponse`` (not the
    original) so the persisted ``messages.content`` is the cleaner
    draft per FR-016, and emits ``shaping_reason='filler_retry'`` plus
    a non-None ``filler_score`` for the persisted draft.
    """
    redispatch_calls: list[str] = []
    clean_response = _make_response(_DIRECT)

    async def _redispatch(delta_text: str) -> ProviderResponse:
        redispatch_calls.append(delta_text)
        return clean_response

    out_response, metadata = await _drive_shape_response(
        original_content=_HEDGE_HEAVY,
        redispatch=_redispatch,
    )

    profile = shaping_module.BEHAVIORAL_PROFILES["anthropic"]
    assert out_response is clean_response
    assert redispatch_calls == [profile.retry_delta_text]
    assert metadata.shaping_reason == shaping_module.SHAPING_REASON_FILLER_RETRY
    assert metadata.filler_score is not None and metadata.filler_score < 0.10
    assert metadata.shaping_retry_delta_text == profile.retry_delta_text


# ---------------------------------------------------------------------------
# T019 -- Acceptance scenario 2: below-threshold -> no retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t019_below_threshold_no_retry_original_persists(
    shaping_on_high_threshold: None,
) -> None:
    """T019 / Scenario 2.

    Given a draft that scores below the (high) threshold, the wiring
    MUST NOT fire any retry. The original ``ProviderResponse`` flows
    through unchanged; metadata records ``shaping_reason=None`` and the
    original draft's ``filler_score`` (no retry fired -> no tightened-
    delta text or retry-dispatch timing recorded).
    """

    async def _redispatch(_delta: str) -> ProviderResponse:
        raise AssertionError(
            "T019: redispatch must not fire when the draft scores below threshold."
        )

    original = _make_response(_DIRECT)
    out_response, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=original,
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    assert out_response is original
    assert metadata.shaping_reason is None
    assert metadata.filler_score is not None and metadata.filler_score < 0.99
    assert metadata.shaping_retry_delta_text is None
    assert metadata.shaping_retry_dispatch_ms is None


# ---------------------------------------------------------------------------
# T020 -- Acceptance scenario 3: master-switch OFF -> NULL metadata + byte-equal
# ---------------------------------------------------------------------------


_NULL_METADATA = ShapingMetadata(
    shaping_score_ms=None,
    shaping_retry_dispatch_ms=None,
    filler_score=None,
    shaping_retry_delta_text=None,
    shaping_reason=None,
)


def _assert_byte_equal_to_pre_feature(out_response: ProviderResponse) -> None:
    """Field-by-field assertion that the response matches a pre-feature row.

    SC-002 byte-equal guarantee: when shaping is off, every
    ``ProviderResponse`` field flows through unchanged from the stub
    factory's defaults. Identity is asserted at the call site; this
    helper covers the field-level invariant separately.
    """
    assert out_response.content == _HEDGE_HEAVY
    assert out_response.input_tokens == 10
    assert out_response.output_tokens == 20
    assert out_response.cost_usd == 0.001
    assert out_response.model == "stub-model"
    assert out_response.latency_ms == 42


@pytest.mark.asyncio
async def test_t020_master_switch_off_returns_null_metadata_byte_equal(
    shaping_off: None,
) -> None:
    """T020 / Scenario 3 + SC-002.

    Distinct from T017 (architectural canary -- asserts no spec 021 code
    path fires under master-switch off). T020 is the row-introspection
    canary: when the master switch is off, ``ShapingMetadata`` has ALL
    FIVE fields ``None`` so every ``routing_log`` row writes NULL into
    the new shaping columns -- no value bleeds through -- AND the
    user-facing ``ProviderResponse`` is byte-equal to a pre-feature run.
    """
    original = _make_response(_HEDGE_HEAVY)  # over-threshold IF shaping were on

    async def _redispatch(_delta: str) -> ProviderResponse:
        raise AssertionError(
            "T020 / SC-002: master-switch-off MUST short-circuit before any retry path."
        )

    out_response, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=original,
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    assert out_response is original
    _assert_byte_equal_to_pre_feature(out_response)
    assert metadata == _NULL_METADATA


# ---------------------------------------------------------------------------
# T021 -- Acceptance scenario 4: both retries above threshold -> exhausted
# ---------------------------------------------------------------------------


# Two distinct hedge-heavy contents per retry so the wiring's content-
# keyed ``_select_response`` can recover the second-retry response (each
# retry contains hedge tokens + a closing marker so both exceed threshold
# and the loop exhausts SHAPING_RETRY_CAP rather than terminating early).
_RETRY_CONTENTS = (
    "I think perhaps it appears the system maybe failed. Hope this helps.",
    "Maybe arguably it seems the system perhaps malfunctioned. Cheers!",
)


@pytest.mark.asyncio
async def test_t021_both_retries_exceed_threshold_marks_exhausted(
    shaping_on: None,
) -> None:
    """T021 / Scenario 4 + SC-003 + FR-004.

    Both retries produce hedge-heavy drafts (always above threshold).
    The loop MUST stop at ``SHAPING_RETRY_CAP=2`` (no infinite loop);
    the second retry's response is persisted; metadata records
    ``shaping_reason='filler_retry_exhausted'`` (NOT
    ``compound_retry_exhausted`` which is the budget-side cap).
    """
    redispatch_calls: list[str] = []

    async def _redispatch(delta_text: str) -> ProviderResponse:
        redispatch_calls.append(delta_text)
        return _make_response(_RETRY_CONTENTS[len(redispatch_calls) - 1])

    original = _make_response(_HEDGE_HEAVY)
    out_response, metadata = await _drive_shape_response(
        original_content=_HEDGE_HEAVY,
        redispatch=_redispatch,
    )
    profile = shaping_module.BEHAVIORAL_PROFILES["anthropic"]
    assert len(redispatch_calls) == shaping_module.SHAPING_RETRY_CAP == 2
    assert redispatch_calls == [profile.retry_delta_text, profile.retry_delta_text]
    assert out_response.content == _RETRY_CONTENTS[1]
    assert out_response is not original
    assert metadata.shaping_reason == shaping_module.SHAPING_REASON_FILLER_RETRY_EXHAUSTED
    assert metadata.filler_score is not None and metadata.filler_score >= 0.10
    assert metadata.shaping_retry_delta_text == profile.retry_delta_text


# ---------------------------------------------------------------------------
# T022 -- Acceptance scenario 5: per-retry routing-log row records all fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t022_routing_log_metadata_records_score_delta_and_timings(
    shaping_on: None,
) -> None:
    """T022 / Scenario 5 + SC-006 + FR-011 + V14 timing.

    When a retry fires, ``ShapingMetadata`` (which the loop hands to
    ``log_routing``) MUST carry the substantive routing-log fields plus
    the two V14 per-stage timing accumulators:

      - ``filler_score``: persisted (post-retry) score, NOT pre-retry.
      - ``shaping_retry_delta_text``: the profile's tightened delta.
      - ``shaping_score_ms`` / ``shaping_retry_dispatch_ms``: V14
        accumulators populated by the timing context (FR-030 cross-ref).
      - ``shaping_reason``: ``filler_retry`` (success path here).
    """
    clean_response = _make_response(_DIRECT)

    async def _redispatch(_delta: str) -> ProviderResponse:
        return clean_response

    _out_response, metadata = await _drive_shape_response(
        original_content=_HEDGE_HEAVY,
        redispatch=_redispatch,
    )
    profile = shaping_module.BEHAVIORAL_PROFILES["anthropic"]
    assert metadata.shaping_reason == shaping_module.SHAPING_REASON_FILLER_RETRY
    assert metadata.filler_score is not None and metadata.filler_score < 0.10
    assert metadata.shaping_retry_delta_text == profile.retry_delta_text
    assert metadata.shaping_score_ms is not None and metadata.shaping_score_ms >= 0
    assert (
        metadata.shaping_retry_dispatch_ms is not None and metadata.shaping_retry_dispatch_ms >= 0
    )
