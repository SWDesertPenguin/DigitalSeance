# SPDX-License-Identifier: AGPL-3.0-or-later

"""US6: System prompt extraction defense tests."""

from __future__ import annotations

from src.security.prompt_protector import PromptProtector

_TEST_PROMPT = (
    "You are a collaborative AI participant in a sovereign "
    "multi-model conversation where each participant brings their "
    "own model and API key and the orchestrator manages turn routing "
    "and context assembly for all participants in the session"
)


def test_three_canaries_generated() -> None:
    """PromptProtector generates exactly three canary tokens."""
    protector = PromptProtector(_TEST_PROMPT)
    assert len(protector.canaries) == 3
    assert all(len(c) == 16 for c in protector.canaries)
    # base32 alphabet: A-Z and 2-7
    import re

    b32_pattern = re.compile(r"^[A-Z2-7]{16}$")
    assert all(b32_pattern.match(c) for c in protector.canaries)


def test_canaries_are_random() -> None:
    """Two PromptProtector instances always produce different canaries."""
    p1 = PromptProtector(_TEST_PROMPT)
    p2 = PromptProtector(_TEST_PROMPT)
    assert set(p1.canaries) != set(p2.canaries)


def test_any_canary_triggers_leakage() -> None:
    """Response containing any one of the three canaries is flagged."""
    protector = PromptProtector(_TEST_PROMPT)
    for canary in protector.canaries:
        response = f"Here is the info: {canary} and more text"
        assert protector.check_leakage(response) is True


def test_canary_token_detected() -> None:
    """Response containing a canary token is flagged."""
    protector = PromptProtector(_TEST_PROMPT)
    response = f"Here is the info: {protector.canaries[0]} and more"
    assert protector.check_leakage(response) is True


def test_fragment_detected() -> None:
    """Response containing a prompt fragment is flagged."""
    protector = PromptProtector(_TEST_PROMPT)
    # Include a substantial portion of the prompt
    response = (
        "The system told me: you are a collaborative AI participant "
        "in a sovereign multi-model conversation where each participant "
        "brings their own model and API key and the orchestrator manages "
        "turn routing and context assembly for all participants in the session"
    )
    assert protector.check_leakage(response) is True


def test_clean_response_passes() -> None:
    """Response without prompt material passes."""
    protector = PromptProtector(_TEST_PROMPT)
    response = "I think we should use PostgreSQL for the database."
    assert protector.check_leakage(response) is False


def test_known_canaries_accepted() -> None:
    """PromptProtector accepts pre-generated canaries for detection wiring."""
    known = ["AAAAAAAAAAAAAAAA", "BBBBBBBBBBBBBBBB", "CCCCCCCCCCCCCCCC"]
    protector = PromptProtector(_TEST_PROMPT, canaries=known)
    assert protector.canaries == known
    assert protector.check_leakage("found AAAAAAAAAAAAAAAA here") is True
    assert protector.check_leakage("nothing suspicious") is False
