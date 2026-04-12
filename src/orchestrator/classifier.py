"""Complexity classifier — pattern-matching heuristic (Phase 1)."""

from __future__ import annotations

import re

_LOW_PATTERNS = [
    r"\b(agree|agreed|confirmed?|acknowledged?)\b",
    r"\b(yes|correct|exactly|right)\b",
    r"\b(sounds good|makes sense|that works)\b",
    r"\b(thanks|thank you|noted)\b",
    r"\b(okay|ok|got it|understood)\b",
]

_HIGH_PATTERNS = [
    r"\b(however|but|although|alternative)\b",
    r"\b(propos(e|al|ing)|suggest(ion|ing)?)\b",
    r"\b(tradeoff|trade-off|drawback|downside)\b",
    r"\b(flaw|problem|issue|concern|risk)\b",
    r"\b(instead|rather|better approach)\b",
    r"\b(disagree|challenge|question|revisit)\b",
    r"\b(synthesiz|integrat|combin)\b",
]

_LOW_RE = [re.compile(p, re.IGNORECASE) for p in _LOW_PATTERNS]
_HIGH_RE = [re.compile(p, re.IGNORECASE) for p in _HIGH_PATTERNS]


def classify(text: str) -> str:
    """Classify text complexity as 'low' or 'high'."""
    high_score = _count_matches(text, _HIGH_RE)
    low_score = _count_matches(text, _LOW_RE)

    if high_score > low_score:
        return "high"
    if low_score > 0 and high_score == 0:
        return "low"
    return "high"  # Default to high when ambiguous


def _count_matches(text: str, patterns: list[re.Pattern]) -> int:
    """Count how many patterns match in the text."""
    return sum(1 for p in patterns if p.search(text))
