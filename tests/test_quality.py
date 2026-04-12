"""US5: Quality detection — n-gram repetition tests."""

from __future__ import annotations

from src.orchestrator.quality import detect_repetition


def test_normal_text_passes() -> None:
    """Diverse text is not flagged as repetitive."""
    text = (
        "This is a thoughtful response about architecture. "
        "We should consider microservices for scalability. "
        "The tradeoff is complexity versus flexibility."
    )
    flagged, score = detect_repetition(text)
    assert flagged is False


def test_highly_repetitive_text_flagged() -> None:
    """Text with excessive repetition is flagged."""
    text = "yes yes yes yes yes yes yes yes yes yes"
    flagged, score = detect_repetition(text)
    assert flagged is True
    assert score > 0.4


def test_empty_text_flagged() -> None:
    """Very short text is flagged."""
    flagged, _ = detect_repetition("")
    assert flagged is True


def test_short_text_flagged() -> None:
    """Text below minimum length is flagged."""
    flagged, _ = detect_repetition("hi")
    assert flagged is True


def test_moderate_repetition_not_flagged() -> None:
    """Some repetition is normal and not flagged."""
    text = (
        "The approach has merit but we need more data. "
        "I think the approach could work with modifications. "
        "Let me suggest a different perspective entirely."
    )
    flagged, _ = detect_repetition(text)
    assert flagged is False
