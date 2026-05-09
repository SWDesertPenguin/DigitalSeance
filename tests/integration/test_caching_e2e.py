# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end test: cache directives reach litellm.acompletion intact.

Uses the mock_litellm fixture (patches litellm.acompletion + completion_cost)
and asserts that dispatch_with_retry forwards cache_control blocks and
prompt_cache_key into the underlying provider call.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from src.api_bridge.caching import BreakpointPosition, CacheDirectives
from src.api_bridge.litellm.dispatch import dispatch_with_retry
from src.database.encryption import encrypt_value


@pytest.fixture
def _encryption_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _enable_caching():
    """Make sure caching is on for these tests regardless of host env."""
    saved = os.environ.pop("SACP_CACHING_ENABLED", None)
    yield
    if saved is None:
        os.environ.pop("SACP_CACHING_ENABLED", None)
    else:
        os.environ["SACP_CACHING_ENABLED"] = saved


def _messages():
    return [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "current"},
    ]


def _encrypted_key(plaintext: str, encryption_key: str) -> str:
    return encrypt_value(plaintext, key=encryption_key)


async def test_anthropic_cache_control_reaches_litellm(
    mock_litellm: SimpleNamespace,
    _encryption_key: str,
):
    api_key_enc = _encrypted_key("k-anthropic", _encryption_key)
    directives = CacheDirectives(
        anthropic_breakpoints=(
            BreakpointPosition.AFTER_SYSTEM,
            BreakpointPosition.AFTER_HISTORY_OLD,
        ),
        anthropic_ttl="1h",
    )
    await dispatch_with_retry(
        model="claude-3-5-sonnet",
        messages=_messages(),
        api_key_encrypted=api_key_enc,
        encryption_key=_encryption_key,
        max_retries=1,
        cache_directives=directives,
    )
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    msgs = call_kwargs["messages"]
    # System (idx 0) and old-history boundary (idx 2) wrapped with cache_control
    assert isinstance(msgs[0]["content"], list)
    assert msgs[0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert isinstance(msgs[2]["content"], list)
    assert msgs[2]["content"][0]["cache_control"]["ttl"] == "1h"


async def test_openai_prompt_cache_key_reaches_litellm(
    mock_litellm: SimpleNamespace,
    _encryption_key: str,
):
    api_key_enc = _encrypted_key("k-openai", _encryption_key)
    directives = CacheDirectives(openai_prompt_cache_key="session-xyz")
    await dispatch_with_retry(
        model="openai/gpt-4o",
        messages=_messages(),
        api_key_encrypted=api_key_enc,
        encryption_key=_encryption_key,
        max_retries=1,
        cache_directives=directives,
    )
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    assert call_kwargs["prompt_cache_key"] == "session-xyz"
    # Messages NOT transformed for OpenAI dispatch
    assert call_kwargs["messages"][0]["content"] == "system prompt"


async def test_gemini_cached_content_reaches_litellm(
    mock_litellm: SimpleNamespace,
    _encryption_key: str,
):
    api_key_enc = _encrypted_key("k-gemini", _encryption_key)
    directives = CacheDirectives(gemini_cached_content_id="cc-abc")
    await dispatch_with_retry(
        model="gemini/gemini-2.5-pro",
        messages=_messages(),
        api_key_encrypted=api_key_enc,
        encryption_key=_encryption_key,
        max_retries=1,
        cache_directives=directives,
    )
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    assert call_kwargs["cached_content"] == "cc-abc"


async def test_no_directives_preserves_byte_identical_payload(
    mock_litellm: SimpleNamespace,
    _encryption_key: str,
):
    """Regression: callers that don't opt in produce the pre-cache payload."""
    api_key_enc = _encrypted_key("k-baseline", _encryption_key)
    msgs = _messages()
    await dispatch_with_retry(
        model="claude-3-5-sonnet",
        messages=msgs,
        api_key_encrypted=api_key_enc,
        encryption_key=_encryption_key,
        max_retries=1,
    )
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    # All message contents stay as plain strings; no cache kwargs leaked in
    for m in call_kwargs["messages"]:
        assert isinstance(m["content"], str)
    assert "prompt_cache_key" not in call_kwargs
    assert "cached_content" not in call_kwargs


async def test_caching_disabled_env_yields_unchanged_payload(
    mock_litellm: SimpleNamespace,
    _encryption_key: str,
):
    os.environ["SACP_CACHING_ENABLED"] = "0"
    api_key_enc = _encrypted_key("k-disabled", _encryption_key)
    directives = CacheDirectives(
        anthropic_breakpoints=(BreakpointPosition.AFTER_SYSTEM,),
        openai_prompt_cache_key="should-not-appear",
    )
    await dispatch_with_retry(
        model="claude-3-5-sonnet",
        messages=_messages(),
        api_key_encrypted=api_key_enc,
        encryption_key=_encryption_key,
        max_retries=1,
        cache_directives=directives,
    )
    call_kwargs = mock_litellm.acompletion.call_args.kwargs
    for m in call_kwargs["messages"]:
        assert isinstance(m["content"], str)
    assert "prompt_cache_key" not in call_kwargs
