# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the known-models max-input-tokens catalog (spec 003 §FR-035)."""

from __future__ import annotations

from unittest.mock import patch

from src.api_bridge.model_limits import known_max_input_tokens


def test_fallback_table_covers_gpt_3_5_turbo():
    """Even with LiteLLM metadata absent, gpt-3.5-turbo resolves to 16,385."""
    with patch("src.api_bridge.model_limits._from_litellm", return_value=None):
        assert known_max_input_tokens("gpt-3.5-turbo") == 16_385


def test_fallback_table_covers_gpt_4o():
    with patch("src.api_bridge.model_limits._from_litellm", return_value=None):
        assert known_max_input_tokens("gpt-4o") == 128_000


def test_fallback_table_covers_claude_sonnet():
    with patch("src.api_bridge.model_limits._from_litellm", return_value=None):
        assert known_max_input_tokens("claude-sonnet-4-6") == 200_000


def test_fallback_table_covers_gemini_flash():
    with patch("src.api_bridge.model_limits._from_litellm", return_value=None):
        assert known_max_input_tokens("gemini-2.5-flash-lite") == 1_000_000


def test_provider_prefix_stripped_for_fallback():
    """anthropic/claude-sonnet-4-6 should match the bare claude-sonnet-4-6 entry."""
    with patch("src.api_bridge.model_limits._from_litellm", return_value=None):
        assert known_max_input_tokens("anthropic/claude-sonnet-4-6") == 200_000
        assert known_max_input_tokens("gemini/gemini-2.5-pro") == 1_000_000
        assert known_max_input_tokens("openai/gpt-4o") == 128_000


def test_unknown_model_returns_none():
    """Models not in LiteLLM metadata or the fallback table return None."""
    with patch("src.api_bridge.model_limits._from_litellm", return_value=None):
        assert known_max_input_tokens("ollama/llama3:8b") is None
        assert known_max_input_tokens("custom/proprietary-model") is None


def test_litellm_metadata_used_when_available():
    """LiteLLM metadata wins when both sources have a value (and disagree below)."""
    with patch("src.api_bridge.model_limits._from_litellm", return_value=12_000):
        # gpt-4 has 8_192 in fallback; with LiteLLM at 12_000, min wins → 8_192
        assert known_max_input_tokens("gpt-4") == 8_192


def test_smallest_value_wins_when_both_sources_present():
    """LiteLLM metadata at 999_999 plus fallback at 16_385 → return 16_385."""
    with patch("src.api_bridge.model_limits._from_litellm", return_value=999_999):
        assert known_max_input_tokens("gpt-3.5-turbo") == 16_385


def test_litellm_only_for_unknown_fallback_entry():
    """Model not in fallback table but present in LiteLLM metadata."""
    with patch("src.api_bridge.model_limits._from_litellm", return_value=42_000):
        assert known_max_input_tokens("some-model-only-litellm-knows") == 42_000


def test_litellm_import_error_falls_back_to_table():
    """If LiteLLM import fails, the fallback table still answers known models."""
    import builtins

    real_import = builtins.__import__

    def deny_litellm(name, *args, **kwargs):
        if name == "litellm":
            raise ImportError("litellm stripped for test")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=deny_litellm):
        assert known_max_input_tokens("gpt-3.5-turbo") == 16_385
