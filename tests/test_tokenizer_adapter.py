# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the per-provider tokenizer adapters (spec 003 §FR-034)."""

from __future__ import annotations

import pytest

from src.api_bridge.tokenizer import (
    AnthropicTokenizer,
    GeminiTokenizer,
    OpenAITokenizer,
    clear_participant_cache,
    default_estimator,
    get_tokenizer_for_model,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_participant_cache()
    yield
    clear_participant_cache()


def test_openai_count_matches_tiktoken_canonical():
    """tiktoken's reference example for cl100k_base."""
    tok = OpenAITokenizer("gpt-4")
    # "tiktoken is great!" tokenises to 6 tokens under cl100k_base
    assert tok.count_tokens("tiktoken is great!") == 6


def test_openai_o200k_for_4o_family():
    tok = OpenAITokenizer("gpt-4o-mini")
    assert tok.get_tokenizer_name() == "openai:o200k_base"


def test_openai_cl100k_for_legacy_family():
    tok = OpenAITokenizer("gpt-4")
    assert tok.get_tokenizer_name() == "openai:cl100k_base"


def test_anthropic_fallback_applies_multiplier():
    tok = AnthropicTokenizer("claude-3-5-sonnet")
    raw = OpenAITokenizer("gpt-4").count_tokens("a moderately sized sentence here")
    anthropic = tok.count_tokens("a moderately sized sentence here")
    # Anthropic fallback is cl100k × 1.10 → at minimum equal to raw
    assert anthropic >= raw


def test_gemini_fallback_applies_multiplier():
    tok = GeminiTokenizer("gemini-2.5-pro")
    raw = OpenAITokenizer("gpt-4").count_tokens("a moderately sized sentence here")
    gemini = tok.count_tokens("a moderately sized sentence here")
    # Gemini fallback is cl100k × 0.95 → at most equal to raw
    assert gemini <= raw


def test_default_estimator_singleton():
    a = default_estimator()
    b = default_estimator()
    assert a is b


def test_default_estimator_counts_nonempty():
    est = default_estimator()
    assert est.count_tokens("hello world") > 0


def test_truncate_returns_empty_for_zero_budget():
    for tok in (
        OpenAITokenizer("gpt-4"),
        AnthropicTokenizer("claude-3-5-sonnet"),
        GeminiTokenizer("gemini-2.5-pro"),
    ):
        assert tok.truncate_to_tokens("hello world this is a longer sentence", 0) == ""


def test_truncate_yields_recountable_prefix():
    """Truncating to N then re-counting stays at or below N."""
    tok = OpenAITokenizer("gpt-4")
    text = "the quick brown fox jumps over the lazy dog repeatedly forever and ever"
    truncated = tok.truncate_to_tokens(text, 5)
    assert tok.count_tokens(truncated) <= 5


def test_truncate_anthropic_recountable():
    tok = AnthropicTokenizer("claude-3-5-sonnet")
    text = "the quick brown fox jumps over the lazy dog repeatedly forever"
    truncated = tok.truncate_to_tokens(text, 10)
    # Anthropic truncates against the smaller raw budget then applies multiplier
    assert tok.count_tokens(truncated) <= 12


def test_truncate_gemini_recountable():
    tok = GeminiTokenizer("gemini-2.5-pro")
    text = "the quick brown fox jumps over the lazy dog repeatedly forever"
    truncated = tok.truncate_to_tokens(text, 10)
    assert tok.count_tokens(truncated) <= 11


def test_factory_routes_anthropic_models():
    assert isinstance(get_tokenizer_for_model("claude-3-5-sonnet"), AnthropicTokenizer)
    assert isinstance(get_tokenizer_for_model("anthropic/claude-3-opus"), AnthropicTokenizer)


def test_factory_routes_openai_models():
    assert isinstance(get_tokenizer_for_model("openai/gpt-4o"), OpenAITokenizer)
    assert isinstance(get_tokenizer_for_model("gpt-4"), OpenAITokenizer)
    assert isinstance(get_tokenizer_for_model("o3-mini"), OpenAITokenizer)


def test_factory_routes_gemini_models():
    assert isinstance(get_tokenizer_for_model("gemini/gemini-2.5-pro"), GeminiTokenizer)
    assert isinstance(get_tokenizer_for_model("vertex_ai/gemini-2.5-flash"), GeminiTokenizer)


def test_factory_unknown_model_falls_back_to_default():
    tok = get_tokenizer_for_model("ollama/llama3:8b")
    # Unknown providers go to the default estimator
    assert tok.get_tokenizer_name() == "default:cl100k"


def test_anthropic_api_path_raises_when_sdk_missing(monkeypatch):
    """Lazy import surface: API path errors clearly when SDK is absent."""
    import builtins

    real_import = builtins.__import__

    def deny_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("anthropic stripped for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_anthropic)
    tok = AnthropicTokenizer("claude-3-5-sonnet")
    with pytest.raises(RuntimeError, match="anthropic SDK not installed"):
        tok.count_tokens_via_api("hello", api_key="sk-test")


def test_gemini_api_path_raises_when_sdk_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def deny_google(name, *args, **kwargs):
        if name == "google.generativeai" or name.startswith("google."):
            raise ImportError("google stripped for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_google)
    tok = GeminiTokenizer("gemini-2.5-pro")
    with pytest.raises(RuntimeError, match="google-generativeai SDK not installed"):
        tok.count_tokens_via_api("hello", api_key="key")
