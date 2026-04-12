"""US6: System prompt extraction defense tests."""

from __future__ import annotations

from src.security.prompt_protector import PromptProtector

_TEST_PROMPT = (
    "You are a collaborative AI participant in a sovereign "
    "multi-model conversation where each participant brings their "
    "own model and API key and the orchestrator manages turn routing "
    "and context assembly for all participants in the session"
)


def test_canary_token_detected() -> None:
    """Response containing canary token is flagged."""
    protector = PromptProtector(_TEST_PROMPT)
    response = f"Here is the info: {protector.canary} and more"
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


def test_canary_is_deterministic() -> None:
    """Same prompt produces same canary token."""
    p1 = PromptProtector(_TEST_PROMPT)
    p2 = PromptProtector(_TEST_PROMPT)
    assert p1.canary == p2.canary


def test_different_prompts_different_canaries() -> None:
    """Different prompts produce different canary tokens."""
    p1 = PromptProtector("Prompt one with enough words here")
    p2 = PromptProtector("Prompt two completely different text")
    assert p1.canary != p2.canary
