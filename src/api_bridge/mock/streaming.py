"""Mock-adapter stream synthesis per spec 020 contracts/stream-event-shape.md."""

from __future__ import annotations

from collections.abc import AsyncIterator

from src.api_bridge.adapter import ProviderResponse, StreamEvent, StreamEventType


def default_stream(response: ProviderResponse) -> list[StreamEvent]:
    """Synthesize the default two-event sequence from a `ProviderResponse`."""
    return [
        StreamEvent(
            event_type=StreamEventType.TEXT_DELTA,
            content=response.content,
        ),
        StreamEvent(
            event_type=StreamEventType.FINALIZATION,
            finish_reason="stop",
            usage={
                "prompt_tokens": response.input_tokens,
                "completion_tokens": response.output_tokens,
            },
        ),
    ]


async def explicit_stream(events: tuple[StreamEvent, ...]) -> AsyncIterator[StreamEvent]:
    """Yield fixture-supplied events verbatim."""
    for event in events:
        yield event
