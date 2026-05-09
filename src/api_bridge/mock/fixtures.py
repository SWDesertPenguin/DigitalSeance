"""Mock adapter fixture loader + matcher per spec 020 contracts.

Loads JSON fixture files from `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`
and matches dispatched inputs against fixture entries in two modes per
research.md §8: hash (sha256 over canonical message-list JSON) and
substring (text-in-last-message). Hash matches win over substring per
the documented resolution algorithm.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.api_bridge.adapter import (
    CanonicalErrorCategory,
    Capabilities,
    ProviderResponse,
    StreamEvent,
    StreamEventType,
)
from src.api_bridge.mock.errors import MockFixtureSchemaError

MatchMode = Literal["hash", "substring"]

_VALID_CATEGORY_VALUES: frozenset[str] = frozenset(item.value for item in CanonicalErrorCategory)


@dataclass(frozen=True, slots=True)
class ResponseFixture:
    match_mode: MatchMode
    match_value: str
    response: ProviderResponse
    stream_events: tuple[StreamEvent, ...] | None = None


@dataclass(frozen=True, slots=True)
class ErrorFixture:
    match_mode: MatchMode
    match_value: str
    canonical_category: CanonicalErrorCategory
    retry_after_seconds: int | None = None
    provider_message: str | None = None


@dataclass(frozen=True, slots=True)
class MockFixtureSet:
    responses: tuple[ResponseFixture, ...]
    errors: tuple[ErrorFixture, ...]
    capabilities: dict[str, Capabilities]


def load(path: str | Path) -> MockFixtureSet:
    """Load + validate a mock fixture file."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MockFixtureSchemaError(f"invalid JSON in {path!r}: {exc}") from exc
    except OSError as exc:
        raise MockFixtureSchemaError(f"cannot read {path!r}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MockFixtureSchemaError(f"top-level value in {path!r} must be a dict")
    return MockFixtureSet(
        responses=_parse_responses(raw.get("responses", [])),
        errors=_parse_errors(raw.get("errors", [])),
        capabilities=_parse_capabilities(raw.get("capabilities", {})),
    )


def canonical_hash(messages: list[dict[str, Any]]) -> str:
    """Stable sha256 over `messages` per research.md §8."""
    payload = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def last_message_text(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    content = messages[-1].get("content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, ensure_ascii=False)


def match_response(
    messages: list[dict[str, Any]], fixtures: tuple[ResponseFixture, ...]
) -> ResponseFixture | None:
    return _match(messages, fixtures)


def match_error(
    messages: list[dict[str, Any]], fixtures: tuple[ErrorFixture, ...]
) -> ErrorFixture | None:
    return _match(messages, fixtures)


def _match(messages: list[dict[str, Any]], fixtures: tuple[Any, ...]) -> Any | None:
    """Hash-mode tried first; substring fallback per research.md §8."""
    if not fixtures:
        return None
    h = canonical_hash(messages)
    for entry in fixtures:
        if entry.match_mode == "hash" and entry.match_value == h:
            return entry
    last = last_message_text(messages)
    for entry in fixtures:
        if entry.match_mode == "substring" and entry.match_value in last:
            return entry
    return None


def _parse_responses(raw: Any) -> tuple[ResponseFixture, ...]:
    if not isinstance(raw, list):
        raise MockFixtureSchemaError("`responses` must be a list")
    return tuple(_parse_response_item(idx, item) for idx, item in enumerate(raw))


def _parse_response_item(idx: int, item: Any) -> ResponseFixture:
    if not isinstance(item, dict):
        raise MockFixtureSchemaError(f"responses[{idx}] must be a dict")
    match_mode, match_value = _parse_match(item.get("match"), f"responses[{idx}]")
    response_raw = item.get("response")
    if not isinstance(response_raw, dict):
        raise MockFixtureSchemaError(f"responses[{idx}].response must be a dict")
    response = _parse_response_payload(response_raw, f"responses[{idx}].response")
    events_raw = item.get("stream_events")
    events = (
        _parse_stream_events(events_raw, f"responses[{idx}].stream_events")
        if events_raw is not None
        else None
    )
    return ResponseFixture(
        match_mode=match_mode, match_value=match_value, response=response, stream_events=events
    )


def _parse_errors(raw: Any) -> tuple[ErrorFixture, ...]:
    if not isinstance(raw, list):
        raise MockFixtureSchemaError("`errors` must be a list")
    return tuple(_parse_error_item(idx, item) for idx, item in enumerate(raw))


def _parse_error_item(idx: int, item: Any) -> ErrorFixture:
    if not isinstance(item, dict):
        raise MockFixtureSchemaError(f"errors[{idx}] must be a dict")
    match_mode, match_value = _parse_match(item.get("match"), f"errors[{idx}]")
    category_raw = item.get("canonical_category")
    if not isinstance(category_raw, str) or category_raw not in _VALID_CATEGORY_VALUES:
        raise MockFixtureSchemaError(
            f"errors[{idx}].canonical_category must be one of "
            f"{sorted(_VALID_CATEGORY_VALUES)}; got {category_raw!r}"
        )
    retry_after = item.get("retry_after_seconds")
    if retry_after is not None and not isinstance(retry_after, int):
        raise MockFixtureSchemaError(f"errors[{idx}].retry_after_seconds must be int or null")
    return ErrorFixture(
        match_mode=match_mode,
        match_value=match_value,
        canonical_category=CanonicalErrorCategory(category_raw),
        retry_after_seconds=retry_after,
        provider_message=item.get("provider_message"),
    )


def _parse_match(raw: Any, path: str) -> tuple[MatchMode, str]:
    if not isinstance(raw, dict):
        raise MockFixtureSchemaError(f"{path}.match must be a dict")
    mode = raw.get("mode")
    value = raw.get("value")
    if mode not in ("hash", "substring"):
        raise MockFixtureSchemaError(
            f"{path}.match.mode must be 'hash' or 'substring'; got {mode!r}"
        )
    if not isinstance(value, str):
        raise MockFixtureSchemaError(f"{path}.match.value must be a string")
    return mode, value


def _parse_response_payload(raw: dict[str, Any], path: str) -> ProviderResponse:
    try:
        # Tolerate both contract field names (prompt/completion) and
        # the codebase's existing field names (input/output) so test
        # authors can use whichever they prefer.
        prompt_tokens = raw.get("input_tokens", raw.get("prompt_tokens", 0))
        completion_tokens = raw.get("output_tokens", raw.get("completion_tokens", 0))
        cost = raw.get("cost_usd", raw.get("cost", 0.0))
        return ProviderResponse(
            content=str(raw.get("content", "")),
            input_tokens=int(prompt_tokens),
            output_tokens=int(completion_tokens),
            cost_usd=float(cost),
            model=str(raw.get("model", "mock-model")),
            latency_ms=int(raw.get("latency_ms", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise MockFixtureSchemaError(f"{path}: invalid response payload: {exc}") from exc


def _parse_stream_events(raw: Any, path: str) -> tuple[StreamEvent, ...]:
    if not isinstance(raw, list):
        raise MockFixtureSchemaError(f"{path} must be a list")
    out: list[StreamEvent] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise MockFixtureSchemaError(f"{path}[{idx}] must be a dict")
        event_type_raw = item.get("event_type")
        try:
            event_type = StreamEventType(event_type_raw)
        except ValueError as exc:
            raise MockFixtureSchemaError(
                f"{path}[{idx}].event_type must be one of "
                f"{[e.value for e in StreamEventType]}; got {event_type_raw!r}"
            ) from exc
        out.append(
            StreamEvent(
                event_type=event_type,
                content=item.get("content"),
                tool_call=item.get("tool_call"),
                finish_reason=item.get("finish_reason"),
                usage=item.get("usage"),
            )
        )
    return tuple(out)


def _parse_capabilities(raw: Any) -> dict[str, Capabilities]:
    if not isinstance(raw, dict):
        raise MockFixtureSchemaError("`capabilities` must be a dict")
    out: dict[str, Capabilities] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            raise MockFixtureSchemaError(f"capabilities[{name!r}] must be a dict")
        try:
            out[name] = Capabilities(
                supports_streaming=bool(value["supports_streaming"]),
                supports_tool_calling=bool(value["supports_tool_calling"]),
                supports_prompt_caching=bool(value["supports_prompt_caching"]),
                max_context_tokens=int(value["max_context_tokens"]),
                tokenizer_name=str(value["tokenizer_name"]),
                recommended_temperature_range=_parse_temp_range(
                    value["recommended_temperature_range"], name
                ),
                provider_family=str(value["provider_family"]),
            )
        except KeyError as exc:
            raise MockFixtureSchemaError(
                f"capabilities[{name!r}]: missing required key {exc}"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise MockFixtureSchemaError(f"capabilities[{name!r}]: invalid value: {exc}") from exc
    return out


def _parse_temp_range(raw: Any, name: str) -> tuple[float, float]:
    if not isinstance(raw, list) or len(raw) != 2:
        raise MockFixtureSchemaError(
            f"capabilities[{name!r}].recommended_temperature_range must be [min, max]"
        )
    return float(raw[0]), float(raw[1])
