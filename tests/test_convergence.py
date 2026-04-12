"""US1+2: Convergence detection — embedding, similarity, divergence."""

from __future__ import annotations

import numpy as np

from src.orchestrator.convergence import (
    ConvergenceDetector,
    _cosine_sim,
)


def _make_embedding(values: list[float]) -> bytes:
    """Create a fake embedding from float values."""
    return np.array(values, dtype=np.float32).tobytes()


def test_identical_embeddings_high_similarity() -> None:
    """Identical vectors have similarity 1.0."""
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert _cosine_sim(a, b) == 1.0


def test_orthogonal_embeddings_zero_similarity() -> None:
    """Orthogonal vectors have similarity 0.0."""
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert abs(_cosine_sim(a, b)) < 0.01


def test_opposite_embeddings_negative_similarity() -> None:
    """Opposite vectors have similarity -1.0."""
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert _cosine_sim(a, b) < 0


def test_is_converging_above_threshold() -> None:
    """Similarity above threshold is flagged as converging."""

    detector = ConvergenceDetector.__new__(ConvergenceDetector)
    detector._threshold = 0.85
    assert detector.is_converging(0.90) is True
    assert detector.is_converging(0.50) is False


def test_should_diverge_on_first_convergence() -> None:
    """First convergence triggers divergence prompt."""
    detector = ConvergenceDetector.__new__(ConvergenceDetector)
    detector._threshold = 0.85
    detector._divergence_prompted = False
    assert detector.should_diverge(0.90) is True


def test_should_not_diverge_twice() -> None:
    """Second convergence does not re-trigger divergence."""
    detector = ConvergenceDetector.__new__(ConvergenceDetector)
    detector._threshold = 0.85
    detector._divergence_prompted = True
    assert detector.should_diverge(0.90) is False


def test_should_escalate_after_divergence() -> None:
    """Continued convergence after divergence triggers escalation."""
    detector = ConvergenceDetector.__new__(ConvergenceDetector)
    detector._threshold = 0.85
    detector._divergence_prompted = True
    assert detector.should_escalate(0.90) is True


def test_divergence_clears_on_low_similarity() -> None:
    """Low similarity clears divergence state."""
    detector = ConvergenceDetector.__new__(ConvergenceDetector)
    detector._threshold = 0.85
    detector._divergence_prompted = True
    # should_diverge with low similarity clears the flag
    detector.should_diverge(0.50)
    assert detector._divergence_prompted is False
