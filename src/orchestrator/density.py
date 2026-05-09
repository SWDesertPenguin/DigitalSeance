# SPDX-License-Identifier: AGPL-3.0-or-later

"""Information-density signal for response-quality validation.

Phase 1 addition to the post-turn quality pipeline. Computes a density
score per turn and flags anomalies vs a session-level rolling baseline.
The signal catches three failure modes documented in the local research
bundle (`comm-design/03-shorthand-and-emergent.md`):

  - terse-register drift: a participant gets shorter without saying less
  - content-free agreement: long response with low information content
  - collusion-on-paper: AIs aligning on a notation that loses meaning

The check is observational in Phase 1 — anomalies are logged to
`convergence_log` with `tier='density_anomaly'`, but no circuit-breaker
trip, no turn skip, no escalation. The Phase 3 calibration pass uses
the artifact emitted by `tests/calibration/test_density_distribution.py`
to retune the default threshold ratio.

Formula (reproducible, deterministic given a fixed embedding model):

    word_count   = len(text.split())
    abs_emb      = |model.encode(text, normalize_embeddings=True)|
    prob_dist    = abs_emb / sum(abs_emb)
    entropy      = -sum(p * log(p) for p in prob_dist if p > 0)
    density      = word_count / (1 + entropy)

Worked example:
    text         = "the quick brown fox" (4 words)
    embedding    = 384-dim float32 (all-MiniLM-L6-v2, normalized)
    entropy      ~ ln(384) ≈ 5.95 (uniform-ish distribution)
    density      = 4 / (1 + 5.95) ≈ 0.575

A higher density means more words per unit embedding entropy — i.e.,
verbose output that doesn't carry proportional semantic load. The
anomaly check fires when density exceeds `ratio × baseline_mean` over
the last 20 turns.
"""

from __future__ import annotations

import math
import os
import statistics
from typing import Any

DEFAULT_THRESHOLD_RATIO = 1.5
BASELINE_WINDOW = 20
_MIN_BASELINE_FOR_CHECK = BASELINE_WINDOW


def get_threshold_ratio() -> float:
    """Read SACP_DENSITY_ANOMALY_RATIO; fall back to 1.5 on unset/invalid.

    Per V6 graceful degradation: invalid env values return the default
    rather than halting the pipeline. The startup validator
    (V16) catches invalid configurations at process start.
    """
    raw = os.environ.get("SACP_DENSITY_ANOMALY_RATIO")
    if not raw:
        return DEFAULT_THRESHOLD_RATIO
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_THRESHOLD_RATIO
    if not 1.0 <= value <= 5.0:
        return DEFAULT_THRESHOLD_RATIO
    return value


def compute_density(text: str, embedding: Any) -> float:
    """Density score for a response given its pre-computed embedding.

    `embedding` is the float32 array produced by the convergence
    detector's call to `model.encode(text, normalize_embeddings=True)`.
    Reusing the array avoids a second encode pass per turn.

    Returns 0.0 for empty / whitespace-only text or when no embedding
    is available (model load failed).
    """
    word_count = len(text.split())
    if word_count == 0 or embedding is None:
        return 0.0
    entropy = _embedding_entropy(embedding)
    return word_count / (1 + entropy)


def compute_density_from_text(text: str, embedding_model: Any) -> float:
    """Convenience wrapper: encode text once, then compute density.

    Useful for unit tests and offline calibration where no convergence
    detector instance is in scope. Production paths reuse the
    convergence detector's already-computed embedding via
    `compute_density`.
    """
    word_count = len(text.split())
    if word_count == 0 or embedding_model is None:
        return 0.0
    embedding = embedding_model.encode(text, normalize_embeddings=True)
    return compute_density(text, embedding)


def _embedding_entropy(embedding: Any) -> float:
    """Shannon entropy of the |embedding| treated as a probability dist."""
    import numpy as np

    abs_vec = np.abs(embedding)
    total = float(abs_vec.sum())
    if total == 0:
        return 0.0
    probs = abs_vec / total
    nonzero = probs[probs > 0]
    return float(-np.sum(nonzero * np.log(nonzero)))


def is_anomaly(
    density: float,
    baseline_window: list[float],
    *,
    ratio: float | None = None,
) -> bool:
    """Decide whether `density` is anomalously high vs the baseline mean.

    Returns False until the baseline contains at least BASELINE_WINDOW
    samples — early-session turns have no stable comparison point.
    """
    if len(baseline_window) < _MIN_BASELINE_FOR_CHECK:
        return False
    threshold = ratio if ratio is not None else get_threshold_ratio()
    mean = statistics.fmean(baseline_window)
    if mean <= 0:
        return False
    return density > threshold * mean


def update_baseline(
    baseline_window: list[float],
    density: float,
) -> list[float]:
    """Append `density` to the rolling window; keep only the last N."""
    if not math.isfinite(density):
        return baseline_window
    return [*baseline_window, density][-BASELINE_WINDOW:]


def baseline_mean(baseline_window: list[float]) -> float | None:
    """Mean of the baseline window, or None when empty."""
    if not baseline_window:
        return None
    return statistics.fmean(baseline_window)
