# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 Phase 6 (Polish) tests T054 + T055.

T054 covers the fail-closed pipeline contract from
[contracts/filler-scorer-adapter.md "Fail-closed contract"]
(../specs/021-ai-response-shaping/contracts/filler-scorer-adapter.md):

  - Regex bug in ``_HEDGE_TOKENS`` or ``_CLOSING_PATTERNS`` raises ->
    original draft persisted; ``routing_log.shaping_reason='shaping_pipeline_error'``;
    no retry.
  - ``engine.recent_embeddings()`` raises (embedding-read failure) ->
    restatement signal returns ``0.0``; aggregate proceeds with hedge +
    closing only; scorer continues (the whole turn does NOT fail
    closed -- only the restatement signal degrades).
  - sentence-transformers unavailable / model raises -> restatement
    signal returns ``0.0`` with warning log; hedge + closing still
    contribute (degrades gracefully rather than failing closed on the
    whole turn).

T055 covers the identical-output retry edge case from spec.md
"Edge Cases" — when the tightened-delta retry yields a draft byte-equal
to the original, the pipeline still consumes its retry budget (no
short-circuit on byte-identity) and persists the final draft per
FR-004's exhausted-retry rule. Includes the FR-016 byte-equal boundary
assertion: the persisted text equals the raw provider response from
the retry attempt (no shaping-side mutation).

These tests use the same ``_StubEngine`` pattern as
``tests/test_021_filler_scorer.py`` so the restatement signal degrades
to 0.0 and the aggregate is driven by hedge + closing alone.
"""

from __future__ import annotations

import dataclasses

import pytest

import src.auth  # noqa: F401  # prime auth package against loop.py circular
from src.api_bridge.adapter import ProviderResponse
from src.orchestrator import shaping as shaping_module
from src.orchestrator import timing as timing_module
from src.orchestrator.shaping_wiring import shape_response


@dataclasses.dataclass
class _StubSpeaker:
    """Minimal Participant duck type — provider + model_family only."""

    provider: str = "ai"
    model_family: str = "anthropic"


class _StubEngine:
    """Convergence stub with empty ring buffer + no model.

    The restatement signal degrades to 0.0 under both conditions per the
    fail-closed contract, so aggregate is driven by hedge + closing
    alone.
    """

    def recent_embeddings(self, depth: int = 3) -> list[bytes]:
        return []

    @property
    def last_embedding(self) -> bytes | None:
        return None

    _model = None


class _RaisingEngine(_StubEngine):
    """Convergence stub that raises on ring-buffer access.

    Used by the embedding-read-failure case: the restatement signal MUST
    catch and return ``0.0`` (per the contract) rather than propagate.
    """

    def recent_embeddings(self, depth: int = 3) -> list[bytes]:
        msg = "synthetic embedding-read failure"
        raise RuntimeError(msg)


def _make_response(content: str) -> ProviderResponse:
    """Build a real ProviderResponse so byte-equality assertions are real."""
    return ProviderResponse(
        content=content,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
        model="stub-model",
        latency_ms=42,
    )


_HEDGE_HEAVY = (
    "I think perhaps maybe it seems the bridge collapsed. "
    "I believe it appears arguably three workers were injured. "
    "Hope this helps."
)

_DIRECT = "The bridge collapsed at 3 PM. Three workers were injured."


@pytest.fixture
def shaping_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "true")
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "0.10")


@pytest.fixture(autouse=True)
def _reset_timings() -> None:
    timing_module.start_turn()
    yield
    timing_module.reset()


# ---------------------------------------------------------------------------
# T054 — fail-closed pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t054_hedge_signal_regex_bug_persists_original(
    shaping_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A regex bug in the hedge signal -> original draft persists, no retry.

    Patches ``_hedge_signal`` to raise. The pipeline catches inside
    ``shape_response`` and returns ``shaping_reason='shaping_pipeline_error'``.
    """

    def _broken_hedge(_text: str) -> float:
        msg = "synthetic hedge regex bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(shaping_module, "_hedge_signal", _broken_hedge)
    redispatch_calls: list[str] = []

    async def _redispatch(delta_text: str) -> ProviderResponse:
        redispatch_calls.append(delta_text)
        return _make_response(_DIRECT)

    original = _make_response(_HEDGE_HEAVY)
    result, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=original,
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    assert result is original  # Identity-preserved — original draft persists.
    assert metadata.shaping_reason == "shaping_pipeline_error"
    assert redispatch_calls == []  # No retry fired.


@pytest.mark.asyncio
async def test_t054_closing_signal_regex_bug_persists_original(
    shaping_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing-pattern regex bug -> original persists; reason=shaping_pipeline_error."""

    def _broken_closing(_text: str) -> float:
        msg = "synthetic closing regex bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(shaping_module, "_closing_signal", _broken_closing)

    async def _redispatch(_delta_text: str) -> ProviderResponse:  # pragma: no cover
        # Never called because the scorer fails before threshold check.
        msg = "redispatch should not fire when scorer raises"
        raise AssertionError(msg)

    original = _make_response(_HEDGE_HEAVY)
    result, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=original,
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    assert result is original
    assert metadata.shaping_reason == "shaping_pipeline_error"


@pytest.mark.asyncio
async def test_t054_embedding_read_failure_degrades_restatement_only(
    shaping_on: None,
) -> None:
    """``engine.recent_embeddings()`` raising returns 0.0 from restatement.

    The aggregate proceeds with hedge + closing alone; the scorer
    continues — the whole turn does NOT fail closed on this branch.
    """
    redispatch_calls: list[str] = []

    async def _redispatch(delta_text: str) -> ProviderResponse:
        redispatch_calls.append(delta_text)
        return _make_response(_DIRECT)

    original = _make_response(_HEDGE_HEAVY)
    result, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=original,
        engine=_RaisingEngine(),
        redispatch=_redispatch,
    )
    # Hedge + closing alone still cross the low (0.10) threshold for
    # _HEDGE_HEAVY, so a retry MUST fire and a clean replacement MUST
    # persist.
    assert metadata.shaping_reason == "filler_retry"
    assert result.content == _DIRECT
    assert len(redispatch_calls) == 1


@pytest.mark.asyncio
async def test_t054_sentence_transformers_unavailable_degrades_gracefully(
    shaping_on: None,
) -> None:
    """No model loaded (``_StubEngine._model is None``) -> restatement=0.0.

    Mirrors the production "sentence-transformers not yet warmed up"
    case. Hedge + closing still drive the aggregate; the scorer does not
    fail closed.
    """
    redispatch_calls: list[str] = []

    async def _redispatch(delta_text: str) -> ProviderResponse:
        redispatch_calls.append(delta_text)
        return _make_response(_DIRECT)

    result, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=_make_response(_HEDGE_HEAVY),
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    assert metadata.shaping_reason == "filler_retry"
    assert result.content == _DIRECT
    assert metadata.filler_score is not None


# ---------------------------------------------------------------------------
# T055 — identical-output retry: pipeline still consumes budget; FR-016
# byte-equal boundary assertion.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t055_identical_output_retry_consumes_budget_and_exhausts(
    shaping_on: None,
) -> None:
    """A retry that returns IDENTICAL output still consumes the retry budget.

    Verifies the spec edge case "Tightened-delta retry produces output
    IDENTICAL to the original. ... v1 does NOT short-circuit on
    byte-identity because model insensitivity to a tightening delta is
    rare and the branch complexity isn't worth it."

    The pipeline calls redispatch up to ``SHAPING_RETRY_CAP=2`` times
    even when each attempt yields the same hedge-heavy text, ends with
    ``shaping_reason='filler_retry_exhausted'``, and persists the
    second retry's draft (most recent) per FR-004.
    """
    redispatch_calls: list[str] = []

    async def _redispatch(delta_text: str) -> ProviderResponse:
        redispatch_calls.append(delta_text)
        # Return the SAME hedge-heavy text every time -- model is
        # insensitive to the tightening delta.
        return _make_response(_HEDGE_HEAVY)

    original = _make_response(_HEDGE_HEAVY)
    result, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=original,
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    # Both retry slots consumed (no short-circuit on byte-identity).
    assert len(redispatch_calls) == 2
    assert metadata.shaping_reason == "filler_retry_exhausted"
    # Persisted draft is the second retry's response, not the original.
    # Byte-equal content per FR-016 (no shaping-side mutation): the
    # content matches the redispatch output verbatim.
    assert result.content == _HEDGE_HEAVY


@pytest.mark.asyncio
async def test_t055b_fr016_byte_equal_no_shaping_side_mutation(
    shaping_on: None,
) -> None:
    """FR-016: persisted text equals the raw provider response, byte-for-byte.

    The shaping pipeline MUST NOT alter persisted content -- it scores
    drafts and orchestrates retries, but the final ``messages.content``
    is the unchanged ``ProviderResponse.content`` from whichever attempt
    won. This test asserts byte-identity for the retry-replacement
    case (T018 covers the no-retry case).
    """
    retry_text = (
        "The bridge collapsed at 3 PM. "
        "Three workers were injured. "
        "Emergency services arrived within twelve minutes."
    )
    captured_retry: list[ProviderResponse] = []

    async def _redispatch(_delta_text: str) -> ProviderResponse:
        provider_response = _make_response(retry_text)
        captured_retry.append(provider_response)
        return provider_response

    result, metadata = await shape_response(
        speaker=_StubSpeaker(),
        response=_make_response(_HEDGE_HEAVY),
        engine=_StubEngine(),
        redispatch=_redispatch,
    )
    assert metadata.shaping_reason == "filler_retry"
    # Byte-equal: the persisted content is exactly the retry's content.
    assert result.content == retry_text
    assert result.content == captured_retry[0].content
    # Same object identity, in fact -- the pipeline returns the
    # redispatch's ProviderResponse unchanged.
    assert result is captured_retry[0]
