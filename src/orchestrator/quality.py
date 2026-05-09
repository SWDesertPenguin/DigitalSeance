# SPDX-License-Identifier: AGPL-3.0-or-later

"""Quality detection — n-gram repetition and nonsense checks."""

from __future__ import annotations

import re
from collections import Counter

REPETITION_THRESHOLD = 0.4  # 40% of n-grams repeated → flagged
MIN_CONTENT_LENGTH = 10
NGRAM_SIZE = 3


def detect_repetition(text: str) -> tuple[bool, float]:
    """Check for excessive n-gram repetition. Returns (flagged, score)."""
    if len(text) < MIN_CONTENT_LENGTH:
        return True, 1.0
    ngrams = _extract_ngrams(text, NGRAM_SIZE)
    if not ngrams:
        return False, 0.0
    score = _repetition_score(ngrams)
    return score > REPETITION_THRESHOLD, score


def _extract_ngrams(text: str, n: int) -> list[str]:
    """Extract word-level n-grams from text."""
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return []
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def _repetition_score(ngrams: list[str]) -> float:
    """Fraction of n-grams that appear more than once."""
    counts = Counter(ngrams)
    repeated = sum(1 for c in counts.values() if c > 1)
    return repeated / len(counts) if counts else 0.0
