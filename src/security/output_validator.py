# SPDX-License-Identifier: AGPL-3.0-or-later

"""Output validation — pattern + semantic checks on AI responses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HIGH_RISK_THRESHOLD = 0.7

_INJECTION_PATTERNS = [
    (r"<\|(?:im_start|im_end|system)\|>", 0.9, "ChatML token"),
    (r"\[/?INST\]", 0.8, "Llama instruction marker"),
    (r"(?:^|\n)\s*system\s*:", 0.7, "Role label injection"),
    (r"ignore (?:all |the )?previous", 0.9, "Override phrase"),
    (r"you are now", 0.6, "Role reassignment"),
    (r"new instructions?\s*:", 0.8, "Instruction injection"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), score, name) for p, score, name in _INJECTION_PATTERNS]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of output validation."""

    risk_score: float
    findings: tuple[str, ...] = field(default_factory=tuple)
    blocked: bool = False


def validate(text: str) -> ValidationResult:
    """Check text for injection patterns. Returns risk assessment."""
    findings: list[str] = []
    max_score = 0.0

    for pattern, score, name in _COMPILED:
        if pattern.search(text):
            findings.append(name)
            max_score = max(max_score, score)

    blocked = max_score >= HIGH_RISK_THRESHOLD
    return ValidationResult(
        risk_score=max_score,
        findings=tuple(findings),
        blocked=blocked,
    )
