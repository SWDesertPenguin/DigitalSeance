# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 T029: shaping-wiring helper unit tests.

Exercises the post-dispatch wiring layer in ``src/orchestrator/shaping_wiring.py``
in isolation from the loop:

  - master-switch guard short-circuits to ``(response, NULL_METADATA)``
    byte-equal across off-state values (unset, empty, ``'false'``,
    ``'False'``, ``'0'``, garbage)
  - human-speaker filter degrades gracefully even when the master switch
    is on (memory ``feedback_exclude_humans_from_dispatch`` defense in
    depth)
  - missing ``BehavioralProfile`` entry for an unknown family degrades
    to ``NULL_METADATA`` rather than raising
  - the system-message patch utility appends the tightened delta with a
    blank-line separator and never mutates the input list
  - ``_classify_reason`` maps ``ShapingDecision`` to the right
    ``routing_log.shaping_reason`` value across the four canonical
    paths (no retry / success retry / exhausted retry /
    compound-bound)

These tests do NOT require a database; the ``ConvergenceDetector`` and
``ProviderResponse`` stand-ins are minimal duck types.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest

import src.auth  # noqa: F401  # prime auth package against loop.py circular
from src.orchestrator.loop import _patch_system_message
from src.orchestrator.shaping import (
    BEHAVIORAL_PROFILES,
    SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED,
    SHAPING_REASON_FILLER_RETRY,
    SHAPING_REASON_FILLER_RETRY_EXHAUSTED,
    FillerScore,
    ShapingDecision,
)
from src.orchestrator.shaping_wiring import (
    ShapingMetadata,
    _classify_reason,
    response_shaping_enabled,
    shape_response,
)

# Minimal stand-ins ---------------------------------------------------------


@dataclasses.dataclass
class _StubResponse:
    """Duck-type stand-in for ProviderResponse.

    Carries just ``content`` so the wiring helpers' field accesses
    (``.content``) succeed; the wiring is content-only at the layer
    under test.
    """

    content: str


@dataclasses.dataclass
class _StubSpeaker:
    """Duck-type stand-in for a Participant.

    Carries the two attributes the wiring helpers read:
    ``provider`` (for the human-filter defense) and ``model_family``
    (for ``profile_for`` lookup).
    """

    provider: str = "anthropic"
    model_family: str = "anthropic"


class _StubEngine:
    """ConvergenceDetector stand-in.

    The off-path tests never reach the engine; we hand it in only as
    a placeholder so ``shape_response`` can pass it on. ``recent_embeddings``
    returns an empty list so even if a path executed it (it shouldn't
    in the off-state tests) the restatement signal degrades to 0.0.
    """

    def recent_embeddings(self, *, depth: int) -> list[bytes]:
        return []

    @property
    def last_embedding(self) -> bytes | None:
        return None

    _model = None


async def _unused_redispatch(_delta_text: str) -> Any:
    raise AssertionError(
        "Master-switch-off / human / unknown-family paths must not " "fire the redispatch closure."
    )


# response_shaping_enabled --------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["true", "TRUE", "True", "1", "  true ", " 1\n"],
)
def test_response_shaping_enabled_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", value)
    assert response_shaping_enabled() is True


@pytest.mark.parametrize(
    "value",
    ["", "false", "False", "0", "no", "  ", "anything-else", "tru"],
)
def test_response_shaping_enabled_falsy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", value)
    assert response_shaping_enabled() is False


def test_response_shaping_enabled_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SACP_RESPONSE_SHAPING_ENABLED", raising=False)
    assert response_shaping_enabled() is False


# shape_response -----------------------------------------------------------


@pytest.mark.asyncio
async def test_shape_response_master_switch_off_returns_null_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-002 byte-equal: off-state returns the original response and ``None`` metadata."""
    monkeypatch.delenv("SACP_RESPONSE_SHAPING_ENABLED", raising=False)
    response = _StubResponse(content="some draft")
    speaker = _StubSpeaker()
    out_response, metadata = await shape_response(
        speaker=speaker,
        response=response,
        engine=_StubEngine(),
        redispatch=_unused_redispatch,
    )
    assert out_response is response
    assert metadata == ShapingMetadata(None, None, None, None, None)


@pytest.mark.asyncio
async def test_shape_response_human_speaker_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``provider == 'human'`` always degrades to NULL metadata even when shaping is on.

    Memory ``feedback_exclude_humans_from_dispatch``: defense in depth at
    the wiring layer because the bug class (humans treated as AI for
    dispatch) keeps recurring.
    """
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "true")
    response = _StubResponse(content="not-an-AI draft")
    speaker = _StubSpeaker(provider="human", model_family="")
    out_response, metadata = await shape_response(
        speaker=speaker,
        response=response,
        engine=_StubEngine(),
        redispatch=_unused_redispatch,
    )
    assert out_response is response
    assert metadata.shaping_reason is None


@pytest.mark.asyncio
async def test_shape_response_unknown_family_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown ``model_family`` logs a warning and persists the original draft.

    Fail-closed contract per contracts/filler-scorer-adapter.md: unknown
    family is a misconfiguration, not a hard failure -- skip shaping for
    this turn rather than tripping the dispatch path.
    """
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "true")
    response = _StubResponse(content="draft")
    speaker = _StubSpeaker(provider="ai", model_family="not-a-real-family")
    out_response, metadata = await shape_response(
        speaker=speaker,
        response=response,
        engine=_StubEngine(),
        redispatch=_unused_redispatch,
    )
    assert out_response is response
    assert metadata.shaping_reason is None


# _patch_system_message ----------------------------------------------------


def test_patch_system_message_appends_with_blank_line() -> None:
    messages = [
        {"role": "system", "content": "TIER1\n\nTIER2"},
        {"role": "user", "content": "hello"},
    ]
    delta = "Reply briefly and directly."
    patched = _patch_system_message(messages, delta)
    assert patched[0]["content"] == "TIER1\n\nTIER2\n\n" + delta
    assert patched[1] == messages[1]
    # Original list MUST NOT be mutated -- each retry sees a fresh copy.
    assert messages[0]["content"] == "TIER1\n\nTIER2"
    assert patched[0] is not messages[0]


def test_patch_system_message_inserts_when_no_system_message() -> None:
    """Defensive: if no system message exists (shouldn't happen on the
    dispatch path), prepend one carrying just the delta."""
    messages = [{"role": "user", "content": "hello"}]
    delta = "be brief"
    patched = _patch_system_message(messages, delta)
    assert patched[0] == {"role": "system", "content": delta}
    assert patched[1] == messages[0]
    assert messages == [{"role": "user", "content": "hello"}]


# _classify_reason --------------------------------------------------------


def _make_score(aggregate: float) -> FillerScore:
    return FillerScore(
        aggregate=aggregate,
        hedge_signal=0.0,
        restatement_signal=0.0,
        closing_signal=0.0,
        evaluated_at=datetime.now(UTC),
    )


def _make_decision(
    *,
    retries_fired: int,
    retry_aggregates: tuple[float, ...] = (),
    exhausted: bool = False,
) -> ShapingDecision:
    return ShapingDecision(
        original_score=_make_score(0.99),
        retries_fired=retries_fired,
        retry_scores=tuple(_make_score(a) for a in retry_aggregates),
        persisted_index=retries_fired,
        exhausted=exhausted,
    )


def test_classify_reason_no_retry() -> None:
    decision = _make_decision(retries_fired=0)
    assert _classify_reason(decision=decision, profile=BEHAVIORAL_PROFILES["anthropic"]) is None


def test_classify_reason_success_retry() -> None:
    """Retry below threshold (success) -> filler_retry."""
    decision = _make_decision(retries_fired=1, retry_aggregates=(0.10,), exhausted=False)
    assert (
        _classify_reason(decision=decision, profile=BEHAVIORAL_PROFILES["anthropic"])
        == SHAPING_REASON_FILLER_RETRY
    )


def test_classify_reason_exhausted() -> None:
    """Both retries above threshold (exhausted) -> filler_retry_exhausted."""
    decision = _make_decision(retries_fired=2, retry_aggregates=(0.99, 0.99), exhausted=True)
    assert (
        _classify_reason(decision=decision, profile=BEHAVIORAL_PROFILES["anthropic"])
        == SHAPING_REASON_FILLER_RETRY_EXHAUSTED
    )


def test_classify_reason_compound_bound() -> None:
    """Compound budget bound the loop with the last retry still above threshold."""
    decision = _make_decision(retries_fired=1, retry_aggregates=(0.99,), exhausted=False)
    # retries_fired=1 < SHAPING_RETRY_CAP=2 AND last >= threshold -> compound
    assert (
        _classify_reason(decision=decision, profile=BEHAVIORAL_PROFILES["anthropic"])
        == SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED
    )
