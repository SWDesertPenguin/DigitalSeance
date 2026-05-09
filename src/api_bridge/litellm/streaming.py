"""LiteLLM stream chunk -> SACP `StreamEvent` normalization.

Per spec 020 FR-009 + contracts/stream-event-shape.md: SACP-internal
streaming events are a single shape (TEXT_DELTA / TOOL_CALL_DELTA /
FINALIZATION). This module converts LiteLLM-emitted chunks (Anthropic-
style and OpenAI-style) into that shape so downstream code never sees
a provider-native event type.

LiteLLM normalizes most of the provider-shape divergence to an OpenAI-
shaped chunk. We translate that into SACP events here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from src.api_bridge.adapter import StreamEvent, StreamEventType


async def normalize_litellm_stream(
    provider_iter: AsyncIterator[Any],
) -> AsyncIterator[StreamEvent]:
    """Convert LiteLLM's async chunk iterator to SACP StreamEvents.

    Handles OpenAI-shaped delta chunks (LiteLLM's normalized form) for
    text deltas, tool-call deltas, and finalization-with-usage. Anthropic
    streams are surfaced via the same OpenAI-compatible delta shape by
    LiteLLM, so the same translation applies.
    """
    final_finish_reason: str | None = None
    final_usage: dict[str, Any] | None = None
    async for chunk in provider_iter:
        events, finish_reason, usage = _events_from_chunk(chunk)
        if finish_reason is not None:
            final_finish_reason = finish_reason
        if usage is not None:
            final_usage = usage
        for event in events:
            yield event
    yield StreamEvent(
        event_type=StreamEventType.FINALIZATION,
        finish_reason=final_finish_reason,
        usage=final_usage,
    )


def _events_from_chunk(
    chunk: Any,
) -> tuple[list[StreamEvent], str | None, dict[str, Any] | None]:
    """Extract zero-or-more SACP events plus terminal-marker fields from one chunk."""
    events: list[StreamEvent] = []
    finish_reason: str | None = None
    for choice in getattr(chunk, "choices", None) or []:
        events.extend(_events_from_delta(getattr(choice, "delta", None)))
        cf = getattr(choice, "finish_reason", None)
        if cf is not None:
            finish_reason = cf
    chunk_usage = getattr(chunk, "usage", None)
    usage = (
        {
            "prompt_tokens": getattr(chunk_usage, "prompt_tokens", 0),
            "completion_tokens": getattr(chunk_usage, "completion_tokens", 0),
        }
        if chunk_usage is not None
        else None
    )
    return events, finish_reason, usage


def _events_from_delta(delta: Any) -> list[StreamEvent]:
    """Pull TEXT_DELTA / TOOL_CALL_DELTA events out of a single choice's delta."""
    if delta is None:
        return []
    out: list[StreamEvent] = []
    content = getattr(delta, "content", None)
    if content:
        out.append(StreamEvent(event_type=StreamEventType.TEXT_DELTA, content=content))
    for tc in getattr(delta, "tool_calls", None) or []:
        out.append(
            StreamEvent(event_type=StreamEventType.TOOL_CALL_DELTA, tool_call=_tool_call_dict(tc))
        )
    return out


def _tool_call_dict(tc: Any) -> dict[str, Any]:
    """Convert a tool-call delta object into the SACP dict shape."""
    if isinstance(tc, dict):
        return dict(tc)
    function = getattr(tc, "function", None)
    name = getattr(function, "name", None) if function is not None else None
    arguments = getattr(function, "arguments", None) if function is not None else None
    return {
        "id": getattr(tc, "id", None),
        "name": name,
        "arguments": arguments,
    }
