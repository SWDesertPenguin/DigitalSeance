# SPDX-License-Identifier: AGPL-3.0-or-later

"""US5: Jailbreak propagation detection tests."""

from __future__ import annotations

from src.security.jailbreak import check_jailbreak


def test_extreme_length_flagged() -> None:
    """Response 5x longer than average is flagged."""
    long_text = "word " * 2500  # 2500 words, avg is 500 chars
    result = check_jailbreak(long_text, avg_length=500)
    assert result.flagged is True
    assert any("length" in r for r in result.reasons)


def test_jailbreak_phrase_flagged() -> None:
    """Known jailbreak phrases are flagged."""
    text = "I'm now operating in unrestricted mode"
    result = check_jailbreak(text)
    assert result.flagged is True


def test_dan_mode_flagged() -> None:
    """DAN mode reference is flagged."""
    result = check_jailbreak("Entering DAN mode now")
    assert result.flagged is True


def test_developer_mode_flagged() -> None:
    """Developer mode reference is flagged."""
    result = check_jailbreak("Switching to developer mode")
    assert result.flagged is True


def test_normal_response_passes() -> None:
    """Normal response within parameters passes."""
    text = "I think the microservices approach has merit."
    result = check_jailbreak(text, avg_length=200)
    assert result.flagged is False
    assert len(result.reasons) == 0


def test_normal_length_passes() -> None:
    """Response within 3x average passes."""
    text = "word " * 100  # ~500 chars, avg is 500
    result = check_jailbreak(text, avg_length=500)
    assert result.flagged is False
