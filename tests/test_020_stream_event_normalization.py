"""US1 acceptance scenario 3: stream event normalization.

Mock provider streams in OpenAI-shaped delta form and assert the SACP
event sequence matches the contract in
`specs/020-provider-adapter-abstraction/contracts/stream-event-shape.md`.
LiteLLM normalizes Anthropic streams into OpenAI-shaped deltas, so a
single normalization path covers both.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from src.api_bridge.adapter import StreamEventType
from src.api_bridge.litellm.streaming import normalize_litellm_stream


def _delta_chunk(
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    chunk = SimpleNamespace(choices=[choice])
    if usage is not None:
        chunk.usage = SimpleNamespace(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
        )
    return chunk


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_text_deltas_normalize() -> None:
    chunks = [
        _delta_chunk(content="hello "),
        _delta_chunk(content="world"),
        _delta_chunk(finish_reason="stop", usage={"prompt_tokens": 10, "completion_tokens": 2}),
    ]
    events = [e async for e in normalize_litellm_stream(_aiter(chunks))]
    assert events[0].event_type == StreamEventType.TEXT_DELTA
    assert events[0].content == "hello "
    assert events[1].event_type == StreamEventType.TEXT_DELTA
    assert events[1].content == "world"
    assert events[-1].event_type == StreamEventType.FINALIZATION
    assert events[-1].finish_reason == "stop"
    assert events[-1].usage == {"prompt_tokens": 10, "completion_tokens": 2}


@pytest.mark.asyncio
async def test_tool_call_deltas_normalize() -> None:
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="search", arguments='{"q":"cats"}'),
    )
    usage = {"prompt_tokens": 5, "completion_tokens": 3}
    chunks = [
        _delta_chunk(tool_calls=[tc]),
        _delta_chunk(finish_reason="tool_calls", usage=usage),
    ]
    events = [e async for e in normalize_litellm_stream(_aiter(chunks))]
    assert events[0].event_type == StreamEventType.TOOL_CALL_DELTA
    assert events[0].tool_call["id"] == "call_1"
    assert events[0].tool_call["name"] == "search"
    assert events[0].tool_call["arguments"] == '{"q":"cats"}'
    assert events[-1].event_type == StreamEventType.FINALIZATION


@pytest.mark.asyncio
async def test_empty_text_deltas_skipped() -> None:
    chunks = [
        _delta_chunk(content=""),  # empty - should be skipped
        _delta_chunk(content="real"),
        _delta_chunk(finish_reason="stop", usage={"prompt_tokens": 3, "completion_tokens": 1}),
    ]
    events = [e async for e in normalize_litellm_stream(_aiter(chunks))]
    text_deltas = [e for e in events if e.event_type == StreamEventType.TEXT_DELTA]
    assert len(text_deltas) == 1
    assert text_deltas[0].content == "real"


@pytest.mark.asyncio
async def test_finalization_always_emitted_even_without_finish_reason() -> None:
    chunks = [_delta_chunk(content="abc")]
    events = [e async for e in normalize_litellm_stream(_aiter(chunks))]
    assert events[-1].event_type == StreamEventType.FINALIZATION
