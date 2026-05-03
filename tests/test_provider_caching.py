"""Unit tests for provider-native cache directive translation.

Covers:
- CacheDirectives type construction
- BreakpointPosition resolution
- Per-provider translation (Anthropic blocks, OpenAI cache_key, Gemini ref)
- Default-None preserves byte-identical payload (regression guard)
- Env-driven kill-switch (SACP_CACHING_ENABLED='0')
- Default-policy builder (build_session_cache_directives)
"""

from __future__ import annotations

import os

import pytest

from src.api_bridge.caching import (
    BreakpointPosition,
    CacheDirectives,
    apply_directives,
    build_session_cache_directives,
    caching_enabled,
    get_anthropic_ttl_default,
    get_openai_retention_default,
)


@pytest.fixture(autouse=True)
def _reset_caching_env():
    """Strip caching env so each test starts from defaults."""
    keys = (
        "SACP_CACHING_ENABLED",
        "SACP_ANTHROPIC_CACHE_TTL",
        "SACP_OPENAI_CACHE_RETENTION",
    )
    saved = {k: os.environ.pop(k, None) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _basic_messages():
    return [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "old turn 1"},
        {"role": "assistant", "content": "old reply 1"},
        {"role": "user", "content": "old turn 2"},
        {"role": "assistant", "content": "recent reply"},
        {"role": "user", "content": "current turn"},
    ]


def test_cache_directives_default_construction():
    d = CacheDirectives()
    assert d.anthropic_breakpoints is None
    assert d.anthropic_ttl == "1h"
    assert d.openai_prompt_cache_key is None
    assert d.openai_prompt_cache_retention is None
    assert d.gemini_cached_content_id is None


def test_breakpoint_position_string_values():
    assert BreakpointPosition.AFTER_SYSTEM.value == "after_system"
    assert BreakpointPosition.AFTER_HISTORY_OLD.value == "after_history_old"
    assert BreakpointPosition.AFTER_HISTORY_RECENT.value == "after_history_recent"


def test_apply_directives_none_returns_messages_unchanged():
    msgs = _basic_messages()
    out, extra = apply_directives(model="claude-3-5-sonnet", messages=msgs, directives=None)
    assert out is msgs
    assert extra == {}


def test_apply_directives_disabled_env_returns_unchanged():
    os.environ["SACP_CACHING_ENABLED"] = "0"
    msgs = _basic_messages()
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_SYSTEM,),
        openai_prompt_cache_key="sess-1",
    )
    out, extra = apply_directives(model="claude-3-5-sonnet", messages=msgs, directives=directives)
    assert out is msgs
    assert extra == {}


def test_anthropic_after_system_wraps_last_system_message():
    msgs = _basic_messages()
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_SYSTEM,),
        anthropic_ttl="1h",
    )
    out, _ = apply_directives(model="claude-3-5-sonnet", messages=msgs, directives=directives)
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    # other messages stay flat-string content
    assert out[1]["content"] == "old turn 1"


def test_anthropic_after_history_old_wraps_correct_index():
    msgs = _basic_messages()
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_HISTORY_OLD,),
    )
    out, _ = apply_directives(model="anthropic/claude-3-opus", messages=msgs, directives=directives)
    # 5 non-system messages; old boundary = non_system[-4] = msgs[2] (assistant: "old reply 1")
    assert isinstance(out[2]["content"], list)
    assert "cache_control" in out[2]["content"][0]
    # other messages keep string content
    assert out[3]["content"] == "old turn 2"


def test_anthropic_multiple_breakpoints_wrap_each_position():
    msgs = _basic_messages()
    directives = CacheDirectives(
        anthropic_breakpoints=(
            BreakpointPosition.AFTER_SYSTEM,
            BreakpointPosition.AFTER_HISTORY_OLD,
        ),
        anthropic_ttl="5m",
    )
    out, _ = apply_directives(model="claude-3-5-sonnet", messages=msgs, directives=directives)
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][0]["cache_control"]["ttl"] == "5m"
    assert isinstance(out[2]["content"], list)
    assert out[2]["content"][0]["cache_control"]["ttl"] == "5m"


def test_anthropic_short_history_skips_old_breakpoint():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_HISTORY_OLD,),
    )
    out, _ = apply_directives(model="claude-3-5-sonnet", messages=msgs, directives=directives)
    # Fewer than 4 non-system messages → no boundary, no transformation
    assert out == msgs


def test_openai_prompt_cache_key_passthrough():
    msgs = _basic_messages()
    directives = CacheDirectives(openai_prompt_cache_key="session-abc")
    out, extra = apply_directives(model="openai/gpt-4o", messages=msgs, directives=directives)
    # Messages unchanged for OpenAI; cache key in extra kwargs
    assert out is msgs
    assert extra["prompt_cache_key"] == "session-abc"


def test_openai_24h_retention_skipped_when_model_not_in_allowlist():
    msgs = _basic_messages()
    directives = CacheDirectives(
        openai_prompt_cache_key="session-abc",
        openai_prompt_cache_retention="24h",
    )
    out, extra = apply_directives(model="openai/gpt-4o", messages=msgs, directives=directives)
    # 24h retention only fires for allowlisted models; allowlist is empty in Phase 1
    assert "prompt_cache_retention" not in extra
    assert extra["prompt_cache_key"] == "session-abc"


def test_gemini_cached_content_reference_passthrough():
    msgs = _basic_messages()
    directives = CacheDirectives(gemini_cached_content_id="cached-content-xyz")
    out, extra = apply_directives(
        model="gemini/gemini-2.5-pro", messages=msgs, directives=directives
    )
    assert out is msgs
    assert extra["cached_content"] == "cached-content-xyz"


def test_anthropic_directives_ignored_for_openai_model():
    msgs = _basic_messages()
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_SYSTEM,),
        openai_prompt_cache_key="sess",
    )
    out, extra = apply_directives(model="openai/gpt-4o", messages=msgs, directives=directives)
    # Anthropic transformation NOT applied to OpenAI dispatch
    assert out is msgs
    assert extra == {"prompt_cache_key": "sess"}


def test_build_session_directives_for_anthropic_includes_breakpoints():
    d = build_session_cache_directives(session_id="s1", model="claude-3-5-sonnet")
    assert d.anthropic_breakpoints is not None
    assert BreakpointPosition.AFTER_SYSTEM in d.anthropic_breakpoints
    assert BreakpointPosition.AFTER_HISTORY_OLD in d.anthropic_breakpoints
    assert d.anthropic_ttl == "1h"


def test_build_session_directives_for_openai_uses_session_id_as_key():
    d = build_session_cache_directives(session_id="sess-42", model="openai/gpt-4o")
    assert d.openai_prompt_cache_key == "sess-42"
    # Anthropic breakpoints NOT applied for non-Anthropic models
    assert d.anthropic_breakpoints is None


def test_build_session_directives_for_gemini_no_explicit_cache():
    d = build_session_cache_directives(session_id="sess-1", model="gemini/gemini-2.5-pro")
    # Gemini relies on implicit caching; no explicit cachedContent reference
    assert d.gemini_cached_content_id is None
    assert d.openai_prompt_cache_key is None


def test_build_session_directives_disabled_returns_empty():
    os.environ["SACP_CACHING_ENABLED"] = "0"
    d = build_session_cache_directives(session_id="s1", model="claude-3-5-sonnet")
    assert d == CacheDirectives()


def test_anthropic_ttl_env_overrides_default():
    os.environ["SACP_ANTHROPIC_CACHE_TTL"] = "5m"
    assert get_anthropic_ttl_default() == "5m"


def test_anthropic_ttl_env_invalid_falls_back_to_1h():
    os.environ["SACP_ANTHROPIC_CACHE_TTL"] = "garbage"
    assert get_anthropic_ttl_default() == "1h"


def test_openai_retention_env_overrides_default():
    os.environ["SACP_OPENAI_CACHE_RETENTION"] = "24h"
    assert get_openai_retention_default() == "24h"


def test_caching_enabled_default_true():
    assert caching_enabled() is True


def test_caching_enabled_zero_returns_false():
    os.environ["SACP_CACHING_ENABLED"] = "0"
    assert caching_enabled() is False


def test_apply_directives_does_not_mutate_input_messages():
    msgs = _basic_messages()
    snapshot = [dict(m) for m in msgs]
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_SYSTEM,),
    )
    apply_directives(model="claude-3-5-sonnet", messages=msgs, directives=directives)
    # Original list and dicts unchanged
    assert msgs == snapshot
