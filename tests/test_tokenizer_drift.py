# SPDX-License-Identifier: AGPL-3.0-or-later

"""Drift assertion: same English-prose text across all three adapters."""

from __future__ import annotations

from src.api_bridge.tokenizer import (
    AnthropicTokenizer,
    GeminiTokenizer,
    OpenAITokenizer,
)

# Roughly 100 tokens of plain English prose.
_REFERENCE = (
    "The orchestrator dispatches a turn whenever the routing policy admits "
    "a participant, the budget enforcer permits the spend, and the cadence "
    "controller has cleared the post-turn delay. Context assembly walks the "
    "five-priority structure in order, never crossing the participant's "
    "context window minus the response reserve and system-prompt estimate."
)


def test_drift_within_documented_margin_for_english_prose():
    """Per the comm-design tokenizer-drift study, English prose lands within
    a tight band across providers; assert the three adapters agree to a
    documented tolerance.
    """
    counts = {
        "openai": OpenAITokenizer("gpt-4").count_tokens(_REFERENCE),
        "anthropic": AnthropicTokenizer("claude-3-5-sonnet").count_tokens(_REFERENCE),
        "gemini": GeminiTokenizer("gemini-2.5-pro").count_tokens(_REFERENCE),
    }
    lowest = min(counts.values())
    highest = max(counts.values())
    drift = (highest - lowest) / lowest
    # Documented prose drift band; widens for code / non-Latin content
    assert drift <= 0.20, f"prose drift {drift:.2%} exceeded the prose band; counts={counts}"


def test_each_adapter_returns_positive_count_for_nonempty_text():
    for tok in (
        OpenAITokenizer("gpt-4"),
        AnthropicTokenizer("claude-3-5-sonnet"),
        GeminiTokenizer("gemini-2.5-pro"),
    ):
        assert tok.count_tokens(_REFERENCE) > 0
