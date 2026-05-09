# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider-native prompt caching directives and translation.

Phase 1 wiring of the dispatch-time `cache_directives` parameter:
defines the CacheDirectives type, the BreakpointPosition enum, and
per-provider translation that the bridge applies before the LiteLLM
call. When `cache_directives` is None (or SACP_CACHING_ENABLED='0'),
callers behave as before — request payloads are byte-identical.

Provider notes carried from the local research bundle:
  - Anthropic's default cache TTL silently dropped from 1h to 5m on
    2026-03-06; SACP defaults to '1h' so multi-minute session cadence
    keeps cache hits warm. Validated per V16 (SACP_ANTHROPIC_CACHE_TTL).
  - OpenAI's `prompt_cache_key` routes a session's calls to the same
    backend, maximising prefix hit rate across per-participant fan-out.
    SACP uses session_id as the key.
  - Gemini 2.5+ implicit caching is automatic; explicit cachedContent
    reference is supported but optional.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

# Default TTL applied when SACP_ANTHROPIC_CACHE_TTL is unset OR invalid
# (validator refuses to bind on invalid; this fallback covers the
# unset-and-pre-validator path during direct module use in tests).
_ANTHROPIC_TTL_DEFAULT: Literal["5m", "1h"] = "1h"

# Models eligible for OpenAI Extended Prompt Caching (24h TTL via
# `prompt_cache_retention="24h"`). Empty in Phase 1 by design — the
# parameter wiring ships, but model activation waits for production
# traffic confirmation per the prompt's "out of scope" call.
_OPENAI_24H_RETENTION_ALLOWLIST: frozenset[str] = frozenset()


class BreakpointPosition(StrEnum):
    """Logical positions for Anthropic cache_control breakpoints.

    The bridge resolves each position to a message-array index against
    the actual messages list at dispatch time. The orchestrator picks
    positions based on the 5-priority context structure (003 §FR-003);
    the bridge owns the structural mapping.
    """

    AFTER_SYSTEM = "after_system"
    AFTER_HISTORY_OLD = "after_history_old"
    AFTER_HISTORY_RECENT = "after_history_recent"


@dataclass(frozen=True, slots=True)
class CacheDirectives:
    """Per-provider cache directives passed through dispatch.

    Every field is optional; None values are no-ops. The bridge layer
    applies only the fields whose provider matches the dispatched model.
    """

    anthropic_breakpoints: tuple[BreakpointPosition, ...] | None = None
    anthropic_ttl: Literal["5m", "1h"] = "1h"
    openai_prompt_cache_key: str | None = None
    openai_prompt_cache_retention: Literal["default", "24h"] | None = None
    gemini_cached_content_id: str | None = None


def get_anthropic_ttl_default() -> Literal["5m", "1h"]:
    """Read SACP_ANTHROPIC_CACHE_TTL; fall back to '1h' on unset/invalid."""
    raw = os.environ.get("SACP_ANTHROPIC_CACHE_TTL", _ANTHROPIC_TTL_DEFAULT)
    if raw in ("5m", "1h"):
        return raw  # type: ignore[return-value]
    return _ANTHROPIC_TTL_DEFAULT


def get_openai_retention_default() -> Literal["default", "24h"]:
    """Read SACP_OPENAI_CACHE_RETENTION; default 'default'."""
    raw = os.environ.get("SACP_OPENAI_CACHE_RETENTION", "default")
    if raw in ("default", "24h"):
        return raw  # type: ignore[return-value]
    return "default"


def caching_enabled() -> bool:
    """SACP_CACHING_ENABLED kill-switch; default on, fail-closed=off."""
    raw = os.environ.get("SACP_CACHING_ENABLED", "1")
    return raw == "1"


def is_anthropic(model: str) -> bool:
    """LiteLLM model-string heuristic for Anthropic dispatch."""
    return model.startswith(("anthropic/", "claude-"))


def is_openai(model: str) -> bool:
    """LiteLLM model-string heuristic for OpenAI dispatch."""
    return model.startswith(("openai/", "gpt-", "o1-", "o3-", "o4-"))


def is_gemini(model: str) -> bool:
    """LiteLLM model-string heuristic for Gemini/Vertex dispatch."""
    return model.startswith(("gemini/", "google/", "vertex_ai/"))


def build_session_cache_directives(
    *,
    session_id: str,
    model: str,
) -> CacheDirectives:
    """Construct default cache directives for a session+model dispatch.

    Phase 1 policy: cache after the system prompt (priority 1) and
    after older history (priority 4-5 boundary). Recent turns
    (priority 2) and the current turn stay uncached at the tail. For
    OpenAI: prompt_cache_key = session_id. Returns an empty
    CacheDirectives when caching is disabled.
    """
    if not caching_enabled():
        return CacheDirectives()
    return CacheDirectives(
        anthropic_breakpoints=_default_breakpoints_for(model),
        anthropic_ttl=get_anthropic_ttl_default(),
        openai_prompt_cache_key=session_id if is_openai(model) else None,
        openai_prompt_cache_retention=get_openai_retention_default(),
        gemini_cached_content_id=None,
    )


def _default_breakpoints_for(model: str) -> tuple[BreakpointPosition, ...] | None:
    """Anthropic-only breakpoints; None for non-Anthropic models."""
    if not is_anthropic(model):
        return None
    return (
        BreakpointPosition.AFTER_SYSTEM,
        BreakpointPosition.AFTER_HISTORY_OLD,
    )


def apply_directives(
    *,
    model: str,
    messages: list[dict[str, Any]],
    directives: CacheDirectives | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Translate directives to (transformed_messages, extra_litellm_kwargs).

    Returns the input messages and an empty kwargs dict when
    directives is None or caching is disabled — preserves
    byte-identical payload shape for non-opted-in callers.
    """
    if directives is None or not caching_enabled():
        return messages, {}
    extra: dict[str, Any] = {}
    if is_anthropic(model) and directives.anthropic_breakpoints:
        messages = _apply_anthropic_cache(
            messages,
            directives.anthropic_breakpoints,
            directives.anthropic_ttl,
        )
    if is_openai(model):
        extra.update(_openai_kwargs(model, directives))
    if is_gemini(model) and directives.gemini_cached_content_id:
        extra["cached_content"] = directives.gemini_cached_content_id
    return messages, extra


def _apply_anthropic_cache(
    messages: list[dict[str, Any]],
    breakpoints: tuple[BreakpointPosition, ...],
    ttl: str,
) -> list[dict[str, Any]]:
    """Wrap message contents with cache_control at each breakpoint."""
    indices = _resolve_breakpoint_indices(messages, breakpoints)
    if not indices:
        return messages
    result = [dict(msg) for msg in messages]
    for index in indices:
        result[index] = _wrap_with_cache_control(result[index], ttl)
    return result


def _resolve_breakpoint_indices(
    messages: list[dict[str, Any]],
    breakpoints: tuple[BreakpointPosition, ...],
) -> list[int]:
    """Map logical breakpoint positions to message-array indices."""
    indices: list[int] = []
    for position in breakpoints:
        index = _resolve_one(messages, position)
        if index is not None and index not in indices:
            indices.append(index)
    return indices


def _resolve_one(
    messages: list[dict[str, Any]],
    position: BreakpointPosition,
) -> int | None:
    """Find the message-array index for a single breakpoint position."""
    if position == BreakpointPosition.AFTER_SYSTEM:
        return _last_system_index(messages)
    if position == BreakpointPosition.AFTER_HISTORY_OLD:
        return _history_old_index(messages)
    if position == BreakpointPosition.AFTER_HISTORY_RECENT:
        return _history_recent_index(messages)
    return None


def _last_system_index(messages: list[dict[str, Any]]) -> int | None:
    """Index of the last system-role message, or None if absent."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "system":
            return i
    return None


def _history_old_index(messages: list[dict[str, Any]]) -> int | None:
    """Boundary index between older history and the recent MVC floor.

    Heuristic: the message immediately before the last 3 non-system
    messages. Returns None when fewer than 4 non-system messages
    exist (no separation between old and recent yet).
    """
    non_system = [i for i, m in enumerate(messages) if m.get("role") != "system"]
    if len(non_system) < 4:
        return None
    return non_system[-4]


def _history_recent_index(messages: list[dict[str, Any]]) -> int | None:
    """Index of the second-to-last non-system message, or None."""
    non_system = [i for i, m in enumerate(messages) if m.get("role") != "system"]
    if len(non_system) < 2:
        return None
    return non_system[-2]


def _wrap_with_cache_control(
    msg: dict[str, Any],
    ttl: str,
) -> dict[str, Any]:
    """Convert message content to a list-of-blocks with cache_control."""
    content = msg.get("content", "")
    blocks = _content_as_blocks(content)
    if blocks:
        last = dict(blocks[-1])
        last["cache_control"] = {"type": "ephemeral", "ttl": ttl}
        blocks[-1] = last
    return {**msg, "content": blocks}


def _content_as_blocks(content: Any) -> list[dict[str, Any]]:
    """Normalise content to a list of typed blocks."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [dict(b) for b in content]
    return []


def _openai_kwargs(model: str, directives: CacheDirectives) -> dict[str, Any]:
    """OpenAI cache kwargs (key + 24h retention if model in allowlist)."""
    out: dict[str, Any] = {}
    if directives.openai_prompt_cache_key:
        out["prompt_cache_key"] = directives.openai_prompt_cache_key
    if directives.openai_prompt_cache_retention == "24h" and _model_supports_24h(model):
        out["prompt_cache_retention"] = "24h"
    return out


def _model_supports_24h(model: str) -> bool:
    """Whether the model is in the Extended Prompt Caching allowlist."""
    return model in _OPENAI_24H_RETENTION_ALLOWLIST
