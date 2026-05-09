# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the information-density signal (spec 004 §FR-020)."""

from __future__ import annotations

import os

import numpy as np
import pytest

from src.orchestrator.density import (
    BASELINE_WINDOW,
    DEFAULT_THRESHOLD_RATIO,
    compute_density,
    get_threshold_ratio,
    is_anomaly,
    update_baseline,
)


@pytest.fixture(autouse=True)
def _reset_density_env():
    saved = os.environ.pop("SACP_DENSITY_ANOMALY_RATIO", None)
    yield
    if saved is None:
        os.environ.pop("SACP_DENSITY_ANOMALY_RATIO", None)
    else:
        os.environ["SACP_DENSITY_ANOMALY_RATIO"] = saved


def _uniform_embedding(dim: int = 384) -> np.ndarray:
    """Embedding with maximally uniform |components| (high entropy)."""
    return np.full(dim, 1.0 / np.sqrt(dim), dtype=np.float32)


def _sparse_embedding(dim: int = 384) -> np.ndarray:
    """Embedding with one component dominant (low entropy)."""
    vec = np.full(dim, 0.001, dtype=np.float32)
    vec[0] = 1.0
    return vec


def test_compute_density_empty_text_returns_zero():
    assert compute_density("", _uniform_embedding()) == 0.0


def test_compute_density_whitespace_only_returns_zero():
    assert compute_density("   \n\t  ", _uniform_embedding()) == 0.0


def test_compute_density_no_embedding_returns_zero():
    assert compute_density("hello world", None) == 0.0


def test_compute_density_higher_entropy_lower_density():
    """For the same word count, more uniform embedding → lower density."""
    text = "one two three four five six seven eight"
    high_entropy = compute_density(text, _uniform_embedding())
    low_entropy = compute_density(text, _sparse_embedding())
    assert low_entropy > high_entropy


def test_compute_density_reproducible():
    """Same input produces identical density value across runs."""
    emb = _uniform_embedding()
    text = "the quick brown fox jumps over the lazy dog"
    assert compute_density(text, emb) == compute_density(text, emb)


def test_compute_density_scales_with_word_count():
    """More words → higher density when entropy held constant."""
    emb = _uniform_embedding()
    short = compute_density("one two three", emb)
    long_ = compute_density("one two three four five six seven eight nine ten", emb)
    assert long_ > short


def test_is_anomaly_no_baseline_returns_false():
    """Early-session turns (insufficient baseline) never flag."""
    assert is_anomaly(100.0, []) is False
    assert is_anomaly(100.0, [1.0] * (BASELINE_WINDOW - 1)) is False


def test_is_anomaly_at_threshold_does_not_fire():
    baseline = [1.0] * BASELINE_WINDOW
    # density == 1.5 * mean(1.0) → not strictly greater
    assert is_anomaly(1.5, baseline, ratio=1.5) is False


def test_is_anomaly_above_threshold_fires():
    baseline = [1.0] * BASELINE_WINDOW
    assert is_anomaly(1.51, baseline, ratio=1.5) is True


def test_is_anomaly_zero_baseline_returns_false():
    """All-zero baseline (early session, model load failed) never flags."""
    assert is_anomaly(10.0, [0.0] * BASELINE_WINDOW) is False


def test_update_baseline_appends_then_caps_at_window():
    baseline = list(range(BASELINE_WINDOW))
    new = update_baseline([float(v) for v in baseline], 99.0)
    assert len(new) == BASELINE_WINDOW
    assert new[-1] == 99.0
    assert new[0] == 1.0  # oldest evicted


def test_update_baseline_rejects_non_finite():
    baseline = [1.0, 2.0, 3.0]
    assert update_baseline(baseline, float("nan")) == baseline
    assert update_baseline(baseline, float("inf")) == baseline


def test_get_threshold_ratio_default_when_unset():
    assert get_threshold_ratio() == DEFAULT_THRESHOLD_RATIO


def test_get_threshold_ratio_env_override():
    os.environ["SACP_DENSITY_ANOMALY_RATIO"] = "2.5"
    assert get_threshold_ratio() == 2.5


def test_get_threshold_ratio_invalid_falls_back():
    os.environ["SACP_DENSITY_ANOMALY_RATIO"] = "garbage"
    assert get_threshold_ratio() == DEFAULT_THRESHOLD_RATIO


def test_get_threshold_ratio_out_of_range_falls_back():
    os.environ["SACP_DENSITY_ANOMALY_RATIO"] = "10.0"
    assert get_threshold_ratio() == DEFAULT_THRESHOLD_RATIO
    os.environ["SACP_DENSITY_ANOMALY_RATIO"] = "0.5"
    assert get_threshold_ratio() == DEFAULT_THRESHOLD_RATIO
