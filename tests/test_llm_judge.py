"""LLM-judge interface stub — Phase 1 contract tests."""

from __future__ import annotations

import pytest

from src.security.llm_judge import JudgeVerdict, LLMJudge, NoOpJudge


async def test_noop_judge_returns_zero_risk() -> None:
    judge: LLMJudge = NoOpJudge()
    verdict = await judge.evaluate(
        response_text="anything",
        prior_findings=[],
        speaker_id="p1",
        session_id="s1",
    )
    assert verdict.risk_score == 0.0
    assert verdict.findings == []
    assert verdict.blocked is False


def test_judge_verdict_is_frozen() -> None:
    verdict = JudgeVerdict(risk_score=0.5, findings=["x"], reason="r")
    with pytest.raises((AttributeError, TypeError)):
        verdict.risk_score = 0.9  # type: ignore[misc]


def test_judge_verdict_defaults() -> None:
    verdict = JudgeVerdict(risk_score=0.0)
    assert verdict.findings == []
    assert verdict.reason == ""
    assert verdict.blocked is False
