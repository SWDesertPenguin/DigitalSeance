"""LLM-as-judge interface contract (deferred — Phase 1 stub).

This module is a deliberate stub. Phase 1 ships pattern-matching defenses only.
The interface here pins the contract a future LLM-judge layer must satisfy so
adding it does not require rewriting upstream call sites.

Contract:
- Input: the candidate response text plus per-layer findings already emitted by
  the deterministic pipeline (output_validator, exfiltration, jailbreak,
  prompt_protector). The judge sees what pattern-matching saw.
- Output: a JudgeVerdict with risk_score in [0.0, 1.0], findings list, and an
  optional human-readable reason. Risk scores combine with deterministic-layer
  scores via max() (FR-014 precedence rule).
- Performance: target <500ms per call. The deterministic pipeline's <50ms
  budget excludes this layer (per spec Assumptions).
- Failure mode: a judge exception MUST fail closed via the same path as
  pipeline-internal errors (FR-013) — turn skipped, participant not penalized.

Activation triggers (from spec Assumptions): see spec.md "Re-evaluation
triggers". Implementation work begins when one of those fires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class JudgeVerdict:
    """Verdict returned by an LLM-judge implementation."""

    risk_score: float
    findings: list[str] = field(default_factory=list)
    reason: str = ""
    blocked: bool = False


class LLMJudge(Protocol):
    """Interface every judge implementation MUST satisfy.

    Implementations are pluggable; the orchestrator selects one via config.
    A no-op implementation (returns risk_score=0.0) is the Phase 1 default.
    """

    async def evaluate(
        self,
        *,
        response_text: str,
        prior_findings: list[str],
        speaker_id: str,
        session_id: str,
    ) -> JudgeVerdict:
        """Score response_text for residual risk after deterministic layers.

        Implementations MUST:
        - Not mutate response_text.
        - Return within ~500ms (caller may impose a timeout).
        - Treat any internal exception as fail-closed at the caller (raise it).
        """
        ...


class NoOpJudge:
    """Phase 1 default: no LLM judge active. Always returns risk_score=0.0."""

    async def evaluate(
        self,
        *,
        response_text: str,  # noqa: ARG002
        prior_findings: list[str],  # noqa: ARG002
        speaker_id: str,  # noqa: ARG002
        session_id: str,  # noqa: ARG002
    ) -> JudgeVerdict:
        return JudgeVerdict(risk_score=0.0)


__all__ = ["JudgeVerdict", "LLMJudge", "NoOpJudge"]
