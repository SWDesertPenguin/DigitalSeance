# Contract: SACP StreamEvent shape

The single SACP-internal event shape covering all provider-native streaming formats per FR-009. Every adapter's `stream(request)` method MUST yield only `StreamEvent` instances; provider-native event shapes (Anthropic `content_block_delta`, OpenAI `delta`, etc.) MUST NOT leak past the adapter boundary.

## Dataclass

```python
from dataclasses import dataclass
from enum import Enum

class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    FINALIZATION = "finalization"

@dataclass(frozen=True)
class StreamEvent:
    event_type: StreamEventType
    content: str | None = None              # populated on TEXT_DELTA
    tool_call: dict | None = None           # populated on TOOL_CALL_DELTA
    finish_reason: str | None = None        # populated on FINALIZATION
    usage: dict | None = None               # populated on FINALIZATION
```

Frozen dataclass keeps every event immutable from creation. Adapters cannot mutate events post-emission, so the orchestrator's split-stream accumulator (sacp-design.md §6.5) reads stable values.

## Field semantics by event type

### `TEXT_DELTA`

Emitted for every fragment of generated text content.

- `content`: non-empty string. The text fragment to append to the accumulated response.
- `tool_call`, `finish_reason`, `usage`: all `None`.

Adapters MUST coalesce zero-length text fragments before emission (no `content=""` events).

### `TOOL_CALL_DELTA`

Emitted for every fragment of a tool-call invocation. Provider streams typically deliver tool calls in pieces (id first, then name, then JSON arguments byte-by-byte); the SACP orchestrator's tool-call accumulator reconstructs the complete call from the deltas.

- `tool_call`: dict with shape `{"id": str, "name": str | None, "arguments": dict | str | None}`.
  - `id`: stable identifier for this tool call within the response (provider supplies; orchestrator uses to merge deltas).
  - `name`: tool name; populated on the first delta where the provider supplies it (typically the first event of the tool call). May be `None` on subsequent deltas.
  - `arguments`: progressive JSON. Provider may stream as a string (OpenAI's `delta.tool_calls[].function.arguments` byte stream) or as a partial dict (Anthropic's `input_json_delta`). Adapter normalizes to whichever shape is most useful for the consumer; current convention is to keep the provider's native shape and let the orchestrator's accumulator handle the merge.
- `content`, `finish_reason`, `usage`: all `None`.

### `FINALIZATION`

Single terminal event for the response. Always the last event in the stream.

- `finish_reason`: provider's finish reason. Common values: `"stop"`, `"length"`, `"tool_calls"`, `"content_filter"`. Adapter MAY normalize but is not required to (orchestrator consumes verbatim).
- `usage`: dict with shape `{"prompt_tokens": int, "completion_tokens": int}`. Token counts from provider response. Required — every `FINALIZATION` event MUST carry usage. If the provider does not supply usage in the stream, the adapter MUST fetch it (e.g., via a non-streaming completion call to the same endpoint, or by counting locally with `count_tokens()`).
- `content`, `tool_call`: both `None`.

## Provider-stream-to-SACP-event normalization

### Anthropic (Messages streaming)

```
provider event              →  SACP event
---------------------------    ----------------
message_start                  (suppressed; carries metadata, no content)
content_block_start            (suppressed; carries content-block boundary, no content)
content_block_delta            TEXT_DELTA(content=<delta_text>)
                                 OR
                               TOOL_CALL_DELTA(tool_call=<input_json_delta unwrapped>)
content_block_stop             (suppressed; closes content block)
message_delta                  (carries finish_reason; held for FINALIZATION)
message_stop                   FINALIZATION(finish_reason=<from message_delta>,
                                            usage=<from message_delta>)
```

Anthropic's `message_delta` carries `delta.stop_reason` and `usage`; the adapter holds these values until `message_stop` and emits a single SACP `FINALIZATION` event combining them.

### OpenAI (Chat Completions streaming)

```
provider event              →  SACP event
---------------------------    ----------------
delta.role (first chunk)       (suppressed; role is implicit in SACP context)
delta.content (text)           TEXT_DELTA(content=<delta.content>)
delta.tool_calls[*]            TOOL_CALL_DELTA(tool_call=<delta.tool_calls[i] dict>)
finish_reason != null          FINALIZATION(finish_reason=<finish_reason>,
                                            usage=<chunk.usage if streamed; else fetched>)
```

OpenAI's streaming responses don't include `usage` by default; adapters set `stream_options={"include_usage": True}` to enable it, or fall back to local `count_tokens()` for the prompt count + provider-reported completion count if the stream doesn't carry usage.

### Ollama / vLLM (OpenAI-compatible)

Same as OpenAI mapping. Both speak OpenAI-compatible Chat Completions; the adapter applies the OpenAI normalization unchanged.

### Mock adapter

Synthesizes plausibly-shaped streams from fixture data. When a fixture's `stream_events` list is provided, mock yields those events verbatim. When absent, mock synthesizes a default sequence:

```python
def _default_stream(response: ProviderResponse) -> list[StreamEvent]:
    return [
        StreamEvent(event_type=StreamEventType.TEXT_DELTA, content=response.content),
        StreamEvent(
            event_type=StreamEventType.FINALIZATION,
            finish_reason="stop",  # mock adapter has no streaming finish_reason source
            usage={"prompt_tokens": response.input_tokens,
                   "completion_tokens": response.output_tokens},
        ),
    ]
```

The mock does NOT emulate provider-specific event ordering or buffering quirks per the resolved mock-fidelity clarification (2026-05-08).

## Buffering and reordering (spec edge case)

When a provider delivers stream events out of causal order — e.g., tool-call deltas interleaved across multiple tool calls in a way that's hard to reconstruct in real time — the adapter MUST buffer and reorder before emitting SACP events. The orchestrator never sees raw provider events, so it cannot disambiguate ordering hazards; that's the adapter's job.

In practice for v1: Anthropic and OpenAI streams are well-ordered within a single response, so no reordering is required. The contract preserves the adapter's authority to reorder if a future provider streams chaotically.

## Error handling during streaming

If the provider drops the connection mid-stream, the adapter raises a provider-native exception (e.g., `litellm.APIConnectionError`). The orchestrator catches it, calls `adapter.normalize_error(exc)`, and discards the partial stream. The orchestrator MUST NOT commit a partial response to the canonical transcript (V17 transcript canonicity).

The mock adapter can simulate mid-stream failure via a fixture entry that yields N events and then raises a `MockStreamingError(canonical_category=...)` that `normalize_error()` maps to the configured category — useful for spec 015 breaker tests.

## Test contract

`tests/test_020_stream_event_normalization.py` MUST cover:

- Anthropic-style stream normalizes to the documented SACP event sequence.
- OpenAI-style stream normalizes to the documented SACP event sequence.
- Tool-call streams reconstruct correctly across `TOOL_CALL_DELTA` events.
- `FINALIZATION` events always carry both `finish_reason` and `usage`.
- Mid-stream provider failure raises and the orchestrator does not commit a partial response.
- Mock adapter's default stream synthesis from a fixture matches the contract.
