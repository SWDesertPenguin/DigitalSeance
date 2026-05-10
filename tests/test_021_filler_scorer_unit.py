# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 Phase 3 (US1) unit tests for the aggregator + orchestrator.

Pure-function unit tests for T026 / T027 / T028 in
``src/orchestrator/shaping.py``:

- ``_aggregate`` + ``compute_filler_score`` (T026): weighted sum of the
  three signal helpers; returns a ``FillerScore`` with the aggregate +
  per-signal breakdown.
- ``profile_for`` + ``threshold_for`` (T027): per-family lookup and
  threshold resolution. ``SACP_FILLER_THRESHOLD`` env var, when set,
  overrides every family's profile default uniformly per research.md
  Sec 9; otherwise the profile's per-family default applies.
- ``evaluate_and_maybe_retry`` (T028): retry orchestrator. Hardcoded
  ``SHAPING_RETRY_CAP=2`` per FR-004; joint cap with the participant's
  compound-retry budget per FR-006.

The acceptance scenarios for US1 (T018-T022) live in
``tests/test_021_filler_scorer.py`` and exercise the orchestrator-level
behavior end-to-end. This file covers the pure-function correctness of
the orchestrator pieces those scenarios depend on.
"""

from __future__ import annotations

import asyncio

import pytest

from src.orchestrator import shaping

# ---------------------------------------------------------------------------
# _FakeEngine -- shared with the signal-helper tests but kept local here so
# the unit suites are self-contained.
# ---------------------------------------------------------------------------


class _FakeEngine:
    """Stub ConvergenceDetector with no-model + empty-buffer behavior.

    The aggregator-level tests don't exercise real embeddings -- the
    restatement signal degrades to 0.0 for both the empty-buffer and
    model-unavailable paths, which is the documented fail-closed
    behavior. Using the fake here keeps unit tests fast and deterministic.
    """

    def __init__(self, embeddings: list[bytes] | None = None, model: object | None = None) -> None:
        self._embeddings = embeddings or []
        self._model = model

    def recent_embeddings(self, depth: int = 3) -> list[bytes]:
        return self._embeddings[-depth:]


# ---------------------------------------------------------------------------
# T026: _aggregate + compute_filler_score
# ---------------------------------------------------------------------------


def test_aggregate_zero_inputs_returns_zero() -> None:
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    assert shaping._aggregate(hedge=0.0, restatement=0.0, closing=0.0, profile=profile) == 0.0


def test_aggregate_one_inputs_clamps_to_one() -> None:
    """Weights sum to 1.0; all-1 inputs aggregate to 1.0 exactly."""
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    score = shaping._aggregate(hedge=1.0, restatement=1.0, closing=1.0, profile=profile)
    assert score == pytest.approx(1.0)


def test_aggregate_uses_per_family_weights() -> None:
    """The aggregate is the weighted sum -- exact arithmetic for known weights."""
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    # Default weights: 0.5 / 0.3 / 0.2.
    score = shaping._aggregate(hedge=1.0, restatement=0.0, closing=0.0, profile=profile)
    assert score == pytest.approx(0.5)
    score = shaping._aggregate(hedge=0.0, restatement=1.0, closing=0.0, profile=profile)
    assert score == pytest.approx(0.3)
    score = shaping._aggregate(hedge=0.0, restatement=0.0, closing=1.0, profile=profile)
    assert score == pytest.approx(0.2)


def test_aggregate_clamps_negative_drift() -> None:
    """Defensive clamp absorbs float rounding drift into [0.0, 1.0]."""
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    score = shaping._aggregate(hedge=-0.0001, restatement=-0.0001, closing=-0.0001, profile=profile)
    assert score == 0.0


def test_compute_filler_score_returns_fillerscore_dataclass() -> None:
    """T026: compute_filler_score returns a FillerScore with all fields populated."""
    engine = _FakeEngine()
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    score = asyncio.run(
        shaping.compute_filler_score(
            draft_text="The bridge collapsed at 3 PM.",
            profile=profile,
            engine=engine,
        )
    )
    assert isinstance(score, shaping.FillerScore)
    assert 0.0 <= score.aggregate <= 1.0
    assert 0.0 <= score.hedge_signal <= 1.0
    assert 0.0 <= score.restatement_signal <= 1.0
    assert 0.0 <= score.closing_signal <= 1.0
    assert score.evaluated_at is not None


def test_compute_filler_score_high_for_hedge_heavy_draft() -> None:
    """A hedge + closing heavy draft scores high relative to a neutral draft."""
    engine = _FakeEngine()
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    neutral = "The bridge collapsed at 3 PM. Three workers were injured."
    heavy = (
        "I think perhaps the bridge maybe collapsed. "
        "It seems three workers were injured. "
        "Hope this helps. Let me know if you need more."
    )
    neutral_score = asyncio.run(
        shaping.compute_filler_score(draft_text=neutral, profile=profile, engine=engine)
    )
    heavy_score = asyncio.run(
        shaping.compute_filler_score(draft_text=heavy, profile=profile, engine=engine)
    )
    assert heavy_score.aggregate > neutral_score.aggregate


def test_compute_filler_score_empty_draft_returns_zero() -> None:
    """Empty draft: every signal is 0.0, aggregate is 0.0."""
    engine = _FakeEngine()
    profile = shaping.BEHAVIORAL_PROFILES["openai"]
    score = asyncio.run(shaping.compute_filler_score(draft_text="", profile=profile, engine=engine))
    assert score.aggregate == 0.0
    assert score.hedge_signal == 0.0
    assert score.restatement_signal == 0.0
    assert score.closing_signal == 0.0


# ---------------------------------------------------------------------------
# T027: profile_for + threshold_for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    ["anthropic", "openai", "gemini", "groq", "ollama", "vllm"],
)
def test_profile_for_returns_known_family(family: str) -> None:
    profile = shaping.profile_for(family)
    assert isinstance(profile, shaping.BehavioralProfile)


def test_profile_for_unknown_family_raises_keyerror() -> None:
    """Fail-loud: unknown family is a misconfigured participant, not a degrade case."""
    with pytest.raises(KeyError):
        shaping.profile_for("unknown_family")


def test_threshold_for_uses_profile_default_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SACP_FILLER_THRESHOLD", raising=False)
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    assert shaping.threshold_for(profile) == profile.default_threshold


def test_threshold_for_uses_profile_default_when_env_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "   ")
    profile = shaping.BEHAVIORAL_PROFILES["gemini"]
    assert shaping.threshold_for(profile) == profile.default_threshold


def test_threshold_for_env_overrides_uniformly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env var, when set, overrides every family's default uniformly per research.md Sec 9."""
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "0.42")
    for family in ("anthropic", "openai", "gemini", "groq", "ollama", "vllm"):
        profile = shaping.BEHAVIORAL_PROFILES[family]
        assert shaping.threshold_for(profile) == pytest.approx(0.42)


def test_threshold_for_env_parse_failure_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runtime drift after startup: a non-float env value falls back with a warning."""
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "not-a-float")
    profile = shaping.BEHAVIORAL_PROFILES["anthropic"]
    with caplog.at_level("WARNING", logger="src.orchestrator.shaping"):
        result = shaping.threshold_for(profile)
    assert result == profile.default_threshold
    assert any("failed to parse at runtime" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# T028: evaluate_and_maybe_retry
# ---------------------------------------------------------------------------


def _profile_with_threshold(threshold: float) -> shaping.BehavioralProfile:
    """Build a BehavioralProfile with a known threshold (and default weights)."""
    return shaping.BehavioralProfile(
        default_threshold=threshold,
        hedge_weight=0.5,
        restatement_weight=0.3,
        closing_weight=0.2,
        retry_delta_text="Reply briefly and directly.",
    )


def _run_evaluate(
    *,
    draft_text: str,
    profile: shaping.BehavioralProfile,
    dispatch,
    compound_budget_remaining: int,
) -> tuple[str, shaping.ShapingDecision, int]:
    """Drive ``evaluate_and_maybe_retry`` against an empty fake engine.

    Wraps the asyncio.run + keyword bookkeeping so individual tests stay
    under the 25-line standards-lint ceiling and read as assertions only.
    """
    return asyncio.run(
        shaping.evaluate_and_maybe_retry(
            draft_text=draft_text,
            profile=profile,
            engine=_FakeEngine(),
            dispatch=dispatch,
            compound_budget_remaining=compound_budget_remaining,
        )
    )


def test_evaluate_below_threshold_returns_original_no_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Score below threshold -> no retry fired; persisted_index=0; retries_consumed=0."""
    monkeypatch.delenv("SACP_FILLER_THRESHOLD", raising=False)
    profile = _profile_with_threshold(0.99)  # very high threshold; nothing crosses

    async def _dispatch(_delta: str) -> str:
        raise AssertionError("dispatch must not fire when score is below threshold")

    persisted, decision, consumed = _run_evaluate(
        draft_text="The build pipeline failed at step 4.",
        profile=profile,
        dispatch=_dispatch,
        compound_budget_remaining=2,
    )
    assert persisted == "The build pipeline failed at step 4."
    assert consumed == 0
    assert decision.retries_fired == 0
    assert decision.retry_scores == ()
    assert decision.persisted_index == 0
    assert decision.exhausted is False


def test_evaluate_first_retry_below_threshold_persists_first_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Score above threshold; first retry below threshold -> first retry persists."""
    monkeypatch.delenv("SACP_FILLER_THRESHOLD", raising=False)
    profile = _profile_with_threshold(0.05)
    calls: list[str] = []

    async def _dispatch(delta: str) -> str:
        calls.append(delta)
        return "The bridge collapsed at 3 PM."

    original = "I think perhaps maybe it seems the bridge collapsed. Hope this helps."
    persisted, decision, consumed = _run_evaluate(
        draft_text=original,
        profile=profile,
        dispatch=_dispatch,
        compound_budget_remaining=2,
    )
    assert persisted == "The bridge collapsed at 3 PM."
    assert consumed == 1
    assert calls == [profile.retry_delta_text]
    assert decision.retries_fired == 1
    assert decision.persisted_index == 1
    assert decision.exhausted is False


def test_evaluate_both_retries_above_threshold_marks_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both retries also above threshold -> second retry persisted; exhausted=True."""
    monkeypatch.delenv("SACP_FILLER_THRESHOLD", raising=False)
    profile = _profile_with_threshold(0.05)  # tight; even hedge-heavy retries cross
    hedge_heavy = (
        "I think perhaps the bridge maybe collapsed. "
        "It seems three workers were injured. "
        "Hope this helps."
    )

    async def _dispatch(_delta: str) -> str:
        return hedge_heavy

    persisted, decision, consumed = _run_evaluate(
        draft_text=hedge_heavy,
        profile=profile,
        dispatch=_dispatch,
        compound_budget_remaining=2,
    )
    assert persisted == hedge_heavy
    assert consumed == 2
    assert decision.retries_fired == 2
    assert decision.persisted_index == 2
    assert decision.exhausted is True


def test_evaluate_compound_budget_zero_fires_no_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compound budget at 0 entry: no retries fire even if the score is above threshold."""
    monkeypatch.delenv("SACP_FILLER_THRESHOLD", raising=False)
    profile = _profile_with_threshold(0.05)

    async def _dispatch(_delta: str) -> str:
        raise AssertionError("dispatch must not fire when compound budget is exhausted")

    hedge_heavy = "I think perhaps it seems maybe."
    persisted, decision, consumed = _run_evaluate(
        draft_text=hedge_heavy,
        profile=profile,
        dispatch=_dispatch,
        compound_budget_remaining=0,
    )
    assert persisted == hedge_heavy
    assert consumed == 0
    assert decision.retries_fired == 0
    # Compound-budget-binding case: NOT exhausted (the caller logs
    # compound_retry_exhausted instead of filler_retry_exhausted).
    assert decision.exhausted is False


def test_evaluate_compound_budget_one_caps_at_one_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compound budget at 1 with score above threshold: exactly one retry fires.

    SHAPING_RETRY_CAP would allow a second retry but the compound budget
    binds. Per FR-006 + tasks.md T028 sub-test: ``exhausted=False`` so the
    caller logs ``compound_retry_exhausted`` rather than
    ``filler_retry_exhausted``.
    """
    monkeypatch.delenv("SACP_FILLER_THRESHOLD", raising=False)
    profile = _profile_with_threshold(0.05)
    hedge_heavy = "I think perhaps it seems maybe."
    calls: list[str] = []

    async def _dispatch(delta: str) -> str:
        calls.append(delta)
        return hedge_heavy

    persisted, decision, consumed = _run_evaluate(
        draft_text=hedge_heavy,
        profile=profile,
        dispatch=_dispatch,
        compound_budget_remaining=1,
    )
    assert persisted == hedge_heavy
    assert consumed == 1
    assert len(calls) == 1
    assert decision.retries_fired == 1
    assert decision.exhausted is False


def test_shaping_retry_cap_constant_is_two() -> None:
    """FR-004: hardcoded shaping retry cap is 2."""
    assert shaping.SHAPING_RETRY_CAP == 2


def test_reason_strings_match_contract() -> None:
    """Reason strings persisted to routing_log.shaping_reason per FR-011."""
    assert shaping.SHAPING_REASON_FILLER_RETRY == "filler_retry"
    assert shaping.SHAPING_REASON_FILLER_RETRY_EXHAUSTED == "filler_retry_exhausted"
    assert shaping.SHAPING_REASON_COMPOUND_RETRY_EXHAUSTED == "compound_retry_exhausted"
    assert shaping.SHAPING_REASON_PIPELINE_ERROR == "shaping_pipeline_error"
