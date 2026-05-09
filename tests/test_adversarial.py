# SPDX-License-Identifier: AGPL-3.0-or-later

"""US4: Adversarial rotation — counter and prompt injection tests."""

from __future__ import annotations

from src.orchestrator.adversarial import AdversarialRotator


def test_fires_at_interval() -> None:
    """Adversarial prompt fires at configured interval."""
    rotator = AdversarialRotator(interval=3)
    for _ in range(3):
        rotator.advance("s1")
    assert rotator.should_inject("s1") is True


def test_does_not_fire_early() -> None:
    """Adversarial prompt does not fire before interval."""
    rotator = AdversarialRotator(interval=5)
    rotator.advance("s1")
    rotator.advance("s1")
    assert rotator.should_inject("s1") is False


def test_rotates_across_participants() -> None:
    """Target index rotates on each reset."""
    rotator = AdversarialRotator(interval=3)
    idx1 = rotator.get_target_index("s1", 3)
    rotator.reset_and_rotate("s1")
    idx2 = rotator.get_target_index("s1", 3)
    assert idx1 != idx2


def test_reset_clears_counter() -> None:
    """Reset sets counter back to zero."""
    rotator = AdversarialRotator(interval=3)
    for _ in range(3):
        rotator.advance("s1")
    assert rotator.should_inject("s1") is True
    rotator.reset_and_rotate("s1")
    assert rotator.should_inject("s1") is False


def test_get_prompt_returns_text() -> None:
    """Prompt text is non-empty."""
    rotator = AdversarialRotator()
    prompt = rotator.get_prompt()
    assert len(prompt) > 0
    assert "weakest assumption" in prompt


def test_separate_sessions_independent() -> None:
    """Different sessions have independent counters."""
    rotator = AdversarialRotator(interval=3)
    for _ in range(3):
        rotator.advance("s1")
    assert rotator.should_inject("s1") is True
    assert rotator.should_inject("s2") is False
