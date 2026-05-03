"""Fallback path verification when SDK round-trip fails."""

from __future__ import annotations

from unittest.mock import patch

from src.api_bridge.tokenizer import (
    AnthropicTokenizer,
    GeminiTokenizer,
    _api_count,
)


def test_anthropic_api_failure_uses_fallback():
    tok = AnthropicTokenizer("claude-3-5-sonnet")
    # Force the lazy import to fail; _api_count should swallow the error
    # and return the in-process fallback count.
    with patch.object(
        AnthropicTokenizer,
        "count_tokens_via_api",
        side_effect=RuntimeError("anthropic SDK not installed"),
    ):
        result = _api_count(tok, "the quick brown fox", api_key="sk-test")
    assert result == tok.count_tokens("the quick brown fox")


def test_gemini_api_failure_uses_fallback():
    tok = GeminiTokenizer("gemini-2.5-pro")
    with patch.object(
        GeminiTokenizer,
        "count_tokens_via_api",
        side_effect=RuntimeError("google-generativeai SDK not installed"),
    ):
        result = _api_count(tok, "the quick brown fox", api_key="key")
    assert result == tok.count_tokens("the quick brown fox")


def test_openai_path_is_pure_fallback_no_api_call():
    """OpenAI runs entirely in-process; no API path even on reconcile."""
    from src.api_bridge.tokenizer import OpenAITokenizer

    tok = OpenAITokenizer("gpt-4o")
    assert _api_count(tok, "the quick brown fox", api_key="sk-test") == tok.count_tokens(
        "the quick brown fox"
    )
