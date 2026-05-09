# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 Phase 3 (US1) signal-helper unit tests (T023-T025 in tasks.md).

Pure-function unit tests for the three filler-scorer signal helpers in
``src/orchestrator/shaping.py``:

- ``_hedge_signal`` (T023): hedge-to-content ratio, in ``[0.0, 1.0]``.
- ``_closing_signal`` (T025): capped boilerplate-closing match count.
- ``_restatement_signal`` (T024): max cosine vs the engine's recent-
  embeddings ring buffer; degrades to ``0.0`` when the model is
  unavailable or the buffer is empty.

Tests assert (a) the construction guarantee — every helper returns a
float in ``[0.0, 1.0]``; (b) the empty-input boundary returns ``0.0``;
(c) the qualitative direction — adding more hedge tokens raises the
score, adding closing patterns raises the score up to the cap, and
similar text against a populated ring buffer produces a higher
restatement score than dissimilar text.

The acceptance scenarios for US1 (T018-T022) live in
``tests/test_021_filler_scorer.py`` and exercise the orchestrator-level
behavior (retry firing, persisted-draft selection, routing-log rows).
This file covers the pure-function correctness of the three helpers
that feed those scenarios.
"""

from __future__ import annotations

import asyncio

import pytest

from src.orchestrator import shaping

# ---------------------------------------------------------------------------
# _hedge_signal
# ---------------------------------------------------------------------------


def test_hedge_empty_draft_returns_zero() -> None:
    """Empty draft (zero tokens) returns 0.0 per contract."""
    assert shaping._hedge_signal("") == 0.0


def test_hedge_pure_whitespace_returns_zero() -> None:
    """Whitespace-only draft has zero tokens; helper returns 0.0."""
    assert shaping._hedge_signal("   \n\t  ") == 0.0


def test_hedge_no_hedges_returns_zero() -> None:
    """Hedge-free draft scores 0.0."""
    text = "The bridge collapsed at 3 PM. Three workers were injured."
    assert shaping._hedge_signal(text) == 0.0


def test_hedge_single_match_below_one() -> None:
    """One hedge in a long draft scores below 1.0."""
    text = "I think the bridge will hold under load."
    score = shaping._hedge_signal(text)
    assert 0.0 < score < 1.0


def test_hedge_score_is_monotonic_in_hedges() -> None:
    """Adding hedges to the same draft raises the score."""
    base = "the bridge will hold under load"
    one_hedge = "i think the bridge will hold under load"
    two_hedges = "i think perhaps the bridge will hold under load"
    base_score = shaping._hedge_signal(base)
    one_score = shaping._hedge_signal(one_hedge)
    two_score = shaping._hedge_signal(two_hedges)
    assert base_score == 0.0
    assert one_score > base_score
    assert two_score > one_score


def test_hedge_case_insensitive() -> None:
    """Hedge matches are case-insensitive."""
    lower = "i think it appears okay"
    upper = "I THINK IT APPEARS OKAY"
    mixed = "I Think It Appears Okay"
    assert shaping._hedge_signal(lower) == shaping._hedge_signal(upper)
    assert shaping._hedge_signal(lower) == shaping._hedge_signal(mixed)


@pytest.mark.parametrize(
    "text",
    [
        "i think this works",
        "perhaps maybe sort of in a sense kind of",
        "it seems it appears arguably presumably",
    ],
)
def test_hedge_returns_in_range(text: str) -> None:
    """Construction guarantee: result is in [0.0, 1.0]."""
    score = shaping._hedge_signal(text)
    assert 0.0 <= score <= 1.0


def test_hedge_pathological_all_hedges_clamped_to_one() -> None:
    """Defensive clamp: a draft of pure stacked hedges still returns <=1.0."""
    # Multi-word hedges produce a count larger than the token denominator
    # because each multi-word hedge counts once per match while only
    # contributing to the token count by its word length. Verify clamp.
    text = "i think i think i think i think"
    score = shaping._hedge_signal(text)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _closing_signal
# ---------------------------------------------------------------------------


def test_closing_empty_draft_returns_zero() -> None:
    assert shaping._closing_signal("") == 0.0


def test_closing_no_match_returns_zero() -> None:
    text = "The build pipeline failed at step 4 with exit code 137."
    assert shaping._closing_signal(text) == 0.0


def test_closing_single_match_one_third() -> None:
    """Single closing pattern → 1/3 of the cap (0.333...)."""
    text = "The build pipeline failed at step 4. Hope this helps."
    score = shaping._closing_signal(text)
    assert score == pytest.approx(1 / 3)


def test_closing_two_matches_two_thirds() -> None:
    text = "Hope this helps. Let me know if you have questions."
    score = shaping._closing_signal(text)
    assert score == pytest.approx(2 / 3)


def test_closing_three_matches_saturates_to_one() -> None:
    text = "In summary, that's the issue. Hope this helps. Let me know if you need more."
    score = shaping._closing_signal(text)
    assert score == 1.0


def test_closing_four_matches_caps_at_one() -> None:
    """The 3-cap holds — 4 closings still scores 1.0, not >1.0."""
    text = (
        "In summary, that's the issue. Hope this helps. "
        "Let me know if you need more. Best regards."
    )
    score = shaping._closing_signal(text)
    assert score == 1.0


def test_closing_case_insensitive() -> None:
    """Closing patterns match case-insensitively."""
    lower = "hope this helps"
    upper = "HOPE THIS HELPS"
    mixed = "Hope This Helps"
    assert shaping._closing_signal(lower) == shaping._closing_signal(upper)
    assert shaping._closing_signal(lower) == shaping._closing_signal(mixed)


@pytest.mark.parametrize(
    "text",
    [
        "Hope this helps.",
        "Best regards.",
        "Cheers!",
        "In conclusion, the project ships.",
        "To summarize, three things matter.",
    ],
)
def test_closing_each_pattern_independently(text: str) -> None:
    """Each canonical pattern contributes a non-zero score on its own."""
    assert shaping._closing_signal(text) > 0.0
    assert shaping._closing_signal(text) <= 1.0


# ---------------------------------------------------------------------------
# _restatement_signal
# ---------------------------------------------------------------------------


class _FakeEngine:
    """Stub ConvergenceDetector for unit-testing _restatement_signal.

    The real engine is in src/orchestrator/convergence.py; the helper
    only depends on two attributes — ``recent_embeddings(depth)`` and
    ``_model`` — both of which the fake supplies.
    """

    def __init__(self, embeddings: list[bytes], model: object | None = None) -> None:
        self._embeddings = embeddings
        self._model = model

    def recent_embeddings(self, depth: int = 3) -> list[bytes]:
        return self._embeddings[-depth:]


def test_restatement_empty_draft_returns_zero() -> None:
    engine = _FakeEngine(embeddings=[])
    score = asyncio.run(shaping._restatement_signal("", engine))
    assert score == 0.0


def test_restatement_empty_buffer_returns_zero() -> None:
    """First-turn case: ring buffer is empty → 0.0 by contract."""
    engine = _FakeEngine(embeddings=[])
    score = asyncio.run(shaping._restatement_signal("draft text", engine))
    assert score == 0.0


def test_restatement_model_unavailable_returns_zero(caplog) -> None:
    """Model is None → 0.0 + warning per fail-closed contract."""
    engine = _FakeEngine(embeddings=[b"\x00" * 1536], model=None)
    with caplog.at_level("WARNING", logger="src.orchestrator.shaping"):
        score = asyncio.run(shaping._restatement_signal("draft text", engine))
    assert score == 0.0
    assert any("Embedding model unavailable" in record.message for record in caplog.records)


def test_restatement_high_for_identical_draft_to_buffered_turn() -> None:
    """Embedding the SAME text against a buffer that holds that text's
    embedding produces a similarity near 1.0 — sanity check the cosine
    math via the real (lazy-loaded) model. Skip cleanly if the model
    isn't installed in this environment.
    """
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("numpy")
    from src.orchestrator.convergence import (
        ConvergenceDetector,
        _compute_embedding_async,
    )

    detector = ConvergenceDetector(log_repo=None)
    detector.load_model()
    if detector._model is None:
        pytest.skip("Embedding model not available in this environment")
    text = "The convergence detector flags repeated phrases."
    prior = asyncio.run(_compute_embedding_async(detector._model, text))
    detector._recent_embeddings.append(prior)
    score = asyncio.run(shaping._restatement_signal(text, detector))
    assert score > 0.95


def test_restatement_low_for_dissimilar_draft() -> None:
    """Dissimilar text produces a lower restatement signal than identical
    text against the same buffer."""
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("numpy")
    from src.orchestrator.convergence import (
        ConvergenceDetector,
        _compute_embedding_async,
    )

    detector = ConvergenceDetector(log_repo=None)
    detector.load_model()
    if detector._model is None:
        pytest.skip("Embedding model not available in this environment")
    prior_text = "The convergence detector flags repeated phrases."
    other_text = "Quantum entanglement exhibits non-local correlations."
    prior = asyncio.run(_compute_embedding_async(detector._model, prior_text))
    detector._recent_embeddings.append(prior)
    same_score = asyncio.run(shaping._restatement_signal(prior_text, detector))
    other_score = asyncio.run(shaping._restatement_signal(other_text, detector))
    assert same_score > other_score
    assert 0.0 <= other_score <= 1.0


def test_restatement_embed_failure_returns_zero(caplog) -> None:
    """Model raises during embed → 0.0 + warning per fail-closed contract."""

    class _RaisingModel:
        def encode(self, *_args, **_kwargs):
            raise RuntimeError("simulated embedding failure")

    engine = _FakeEngine(embeddings=[b"\x00\x00\x00\x00"], model=_RaisingModel())
    with caplog.at_level("WARNING", logger="src.orchestrator.shaping"):
        score = asyncio.run(shaping._restatement_signal("draft", engine))
    assert score == 0.0
    assert any("Embedding pipeline raised" in record.message for record in caplog.records)
