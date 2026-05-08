# Contract: Mock adapter fixture file format

JSON fixture file consumed by `MockAdapter` from the path in `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`. Loaded once at adapter instantiation; immutable thereafter. Per [research.md §7](../research.md), JSON was selected over YAML to avoid a runtime dependency.

## Top-level shape

```json
{
  "responses": [...],
  "errors": [...],
  "capabilities": {...}
}
```

All three keys are optional — a fixture file with only `capabilities` is valid for capability-only tests; one with only `errors` is valid for circuit-breaker tests; etc.

## `responses` entries

```json
{
  "match": {"mode": "hash", "value": "<sha256-hex>"},
  "response": {
    "content": "hello world",
    "prompt_tokens": 42,
    "completion_tokens": 10,
    "model": "mock-model",
    "finish_reason": "stop",
    "cost": 0.0,
    "latency_ms": 5,
    "provider_family": "mock"
  },
  "stream_events": [
    {"event_type": "text_delta", "content": "hello "},
    {"event_type": "text_delta", "content": "world"},
    {"event_type": "finalization", "finish_reason": "stop",
     "usage": {"prompt_tokens": 42, "completion_tokens": 10}}
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `match.mode` | yes | `"hash"` or `"substring"` per [research.md §8](../research.md). |
| `match.value` | yes | sha256 hex (hash mode) or substring text (substring mode). |
| `response` | yes | Maps to `ProviderResponse` dataclass. All seven fields populated; see field semantics in [data-model.md](../data-model.md). |
| `stream_events` | no | Optional explicit stream sequence. When omitted, mock synthesizes the default two-event sequence per [stream-event-shape.md](./stream-event-shape.md). |

## `errors` entries

```json
{
  "match": {"mode": "substring", "value": "trigger 5xx"},
  "canonical_category": "error_5xx",
  "retry_after_seconds": null,
  "provider_message": "mock provider unavailable"
}
```

| Field | Required | Notes |
|---|---|---|
| `match.mode` | yes | Same as `responses` entries. |
| `match.value` | yes | Same as `responses` entries. |
| `canonical_category` | yes | One of: `"error_5xx"`, `"error_4xx"`, `"auth_error"`, `"rate_limit"`, `"timeout"`, `"quality_failure"`, `"unknown"` (the seven `CanonicalErrorCategory` values). |
| `retry_after_seconds` | no | Integer or null. Required when `canonical_category="rate_limit"` if the test depends on the breaker honoring a retry-after; nullable otherwise. |
| `provider_message` | no | Free-form provider detail string for `routing_log`. |

When a fixture's `match` succeeds, `MockAdapter.dispatch_with_retry()` raises a `MockInjectedError` that carries the configured canonical category; `normalize_error(exc)` returns a `CanonicalError` with the configured `canonical_category` and `retry_after_seconds`.

## `capabilities` entries

```json
{
  "default": {
    "supports_streaming": true,
    "supports_tool_calling": true,
    "supports_prompt_caching": false,
    "max_context_tokens": 200000,
    "tokenizer_name": "mock-tokenizer",
    "recommended_temperature_range": [0.0, 1.0],
    "provider_family": "mock"
  },
  "no_tool_model": {
    "supports_streaming": true,
    "supports_tool_calling": false,
    "supports_prompt_caching": false,
    "max_context_tokens": 8192,
    "tokenizer_name": "mock-tokenizer",
    "recommended_temperature_range": [0.0, 1.0],
    "provider_family": "mock"
  }
}
```

Top-level keys are capability-set names. The mock adapter's `capabilities(model)` consults a per-test `capability_set` knob (default `"default"`) and returns the named set's values.

| Field | Required | Notes |
|---|---|---|
| `supports_streaming` | yes | Boolean. |
| `supports_tool_calling` | yes | Boolean. Spec 018 routes to `[NEED:]` proxy when `false`. |
| `supports_prompt_caching` | yes | Boolean. Spec 017 freshness logic gates on this. |
| `max_context_tokens` | yes | Positive integer ≥ 1024 per data-model validation rule. |
| `tokenizer_name` | yes | String identifier. |
| `recommended_temperature_range` | yes | Two-element array `[min, max]` with `0.0 ≤ min ≤ max ≤ 2.0`. |
| `provider_family` | yes | String. For mock fixtures, typically `"mock"`; tests that simulate a specific family use that family's name (e.g., `"anthropic"`) so spec 016 metric tests exercise the bounded-enum mapping. |

## Match-key resolution algorithm

Per [research.md §8](../research.md):

1. Compute `canonical_hash = sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False))`.
2. Iterate `responses`; first entry with `match.mode == "hash"` and `match.value == canonical_hash` wins (TEXT or stream).
3. If no hash match, iterate `responses` again; first entry with `match.mode == "substring"` and `match.value in messages[-1]["content"]` wins.
4. If neither matched in `responses`, repeat steps 2-3 against `errors`. If an error entry matches, the dispatch raises `MockInjectedError` with the configured canonical category.
5. If no entry in either list matched, raise `MockFixtureMissing(canonical_hash, last_message_text)` per FR-007. The exception MUST name the missing fixture key (canonical hash + a substring of the last message) so the test author can write the fixture.

## Schema validation at load time

`MockFixtureSet._load(path)` validates:

- File parses as JSON.
- Top-level value is a dict.
- `responses` and `errors` (if present) are lists.
- `capabilities` (if present) is a dict.
- Every `responses` entry has required keys with correct types.
- Every `errors` entry has required keys; `canonical_category` is one of the seven enum values.
- Every `capabilities` entry has all seven required fields.

Schema failure raises `MockFixtureSchemaError` at adapter init time, BEFORE the orchestrator binds ports — V16 fail-closed contract per `contracts/env-vars.md`.

## Sample fixture sets

The repository ships three sample fixtures under `tests/fixtures/mock_adapter/`:

- `basic_responses.json` — minimal hash-and-substring matches for the regression-test path.
- `error_modes.json` — one entry per canonical category for spec 015 breaker tests.
- `streaming_sequences.json` — explicit `stream_events` lists demonstrating the SACP `StreamEvent` shape per `contracts/stream-event-shape.md`.

These samples are reference implementations; tests may load custom fixtures via the `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` env var.

## Fixture maintenance

When the canonical message format changes (e.g., a new field added to message dicts that affects the hash), all hash-mode fixtures need their `match.value` recomputed. Tests that need stable replay across format changes SHOULD use substring mode; tests that need byte-identical replay accept the hash-recomputation cost.

A helper script `scripts/compute_mock_fixture_hash.py` (lands with the implementation tasks) reads a message-list JSON file from stdin and prints the canonical sha256 hex, so test authors can populate hash-mode fixtures without writing inline hash code.
