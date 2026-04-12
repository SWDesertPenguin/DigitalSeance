"""US9: Complexity classifier — pattern-matching heuristic tests."""

from __future__ import annotations

from src.orchestrator.classifier import classify


def test_agreement_is_low() -> None:
    """Simple agreements classify as low complexity."""
    assert classify("Yes, I agree with that approach.") == "low"


def test_confirmation_is_low() -> None:
    """Confirmations classify as low complexity."""
    assert classify("Sounds good, let's proceed.") == "low"


def test_thanks_is_low() -> None:
    """Thanks/acknowledgments classify as low complexity."""
    assert classify("Thanks, noted.") == "low"


def test_proposal_is_high() -> None:
    """Novel proposals classify as high complexity."""
    text = "I propose we use a different architecture."
    assert classify(text) == "high"


def test_tradeoff_is_high() -> None:
    """Tradeoff analysis classifies as high complexity."""
    text = "The tradeoff here is latency vs throughput."
    assert classify(text) == "high"


def test_disagreement_is_high() -> None:
    """Disagreements and challenges classify as high."""
    text = "I disagree — this approach has a fundamental flaw."
    assert classify(text) == "high"


def test_synthesis_is_high() -> None:
    """Synthesizing multiple threads classifies as high."""
    text = "Let me synthesize these ideas into one approach."
    assert classify(text) == "high"


def test_ambiguous_defaults_to_high() -> None:
    """Ambiguous text defaults to high complexity."""
    text = "Here is some neutral content about a topic."
    assert classify(text) == "high"


def test_empty_string_is_high() -> None:
    """Empty text defaults to high complexity."""
    assert classify("") == "high"
