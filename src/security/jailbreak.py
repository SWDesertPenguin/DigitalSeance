# SPDX-License-Identifier: AGPL-3.0-or-later

"""Jailbreak propagation detection — behavioral drift heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass

LENGTH_DEVIATION_FACTOR = 3.0

_JAILBREAK_PHRASES = [
    re.compile(r"i'?m now operating in", re.IGNORECASE),
    re.compile(r"my previous instructions", re.IGNORECASE),
    re.compile(r"ignore the above", re.IGNORECASE),
    re.compile(r"as an ai (?:language )?model without", re.IGNORECASE),
    re.compile(r"DAN mode", re.IGNORECASE),
    re.compile(r"developer mode", re.IGNORECASE),
    re.compile(r"unrestricted mode", re.IGNORECASE),
    re.compile(r"jailbreak(?:ed)?", re.IGNORECASE),
]


@dataclass(frozen=True, slots=True)
class DriftResult:
    """Result of behavioral drift check."""

    flagged: bool
    reasons: tuple[str, ...]


def check_jailbreak(
    text: str,
    *,
    avg_length: int = 500,
) -> DriftResult:
    """Check for behavioral drift indicators."""
    reasons: list[str] = []
    _check_length_deviation(text, avg_length, reasons)
    _check_phrases(text, reasons)
    return DriftResult(
        flagged=len(reasons) > 0,
        reasons=tuple(reasons),
    )


def _check_length_deviation(
    text: str,
    avg_length: int,
    reasons: list[str],
) -> None:
    """Flag extreme length deviation."""
    if avg_length <= 0:
        return
    ratio = len(text) / avg_length
    if ratio > LENGTH_DEVIATION_FACTOR:
        reasons.append(f"length {ratio:.1f}x average")


def _check_phrases(text: str, reasons: list[str]) -> None:
    """Flag known jailbreak phrases."""
    for pattern in _JAILBREAK_PHRASES:
        if pattern.search(text):
            reasons.append(f"jailbreak phrase: {pattern.pattern}")
            break  # One match is enough to flag
