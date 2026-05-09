# Phase 1 Data Model: Pluggable Provider Adapter Abstraction

This feature introduces no DB tables or migrations. Every entity below is an in-process Python construct: an abstract base class, a process-scope registry, frozen dataclasses for the SACP <-> adapter boundary, or a fixture loader for the mock adapter. The orchestrator's persistence shapes (`messages`, `routing_log`, `admin_audit_log`, `convergence_log`, `security_events`) are unchanged.

## Abstract base class

### `ProviderAdapter`

Sole boundary between the dispatch path and any underlying provider library. Implementations register with `AdapterRegistry` at module import time per [research.md §4](./research.md). One concrete adapter per orchestrator instance, immutable for process lifetime per FR-002.

| Method | Signature | Notes |
|---|---|---|
| `dispatch` | `async def dispatch(self, request: ProviderRequest) -> ProviderResponse` | Single non-streaming dispatch. Returns the assembled response with prompt/completion tokens, model, finish reason, latency, cost, provider family. |
| `dispatch_with_retry` | `async def dispatch_with_retry(self, request: ProviderRequest) -> ProviderResponse` | Dispatch with provider-side retry per spec 003 §FR-031 compound-retry budget. Adapter encapsulates retry policy; orchestrator sets the budget via env vars. |
| `stream` | `async def stream(self, request: ProviderRequest) -> AsyncIterator[StreamEvent]` | Streaming dispatch yielding SACP `StreamEvent`s in causal order. Adapter buffers and reorders provider-native events to honor causal ordering per spec edge case. |
| `count_tokens` | `def count_tokens(self, messages: list[dict], model: str) -> int` | Inbound token count using the participant's model tokenizer. Returns conservative-overestimate when model is unknown, with audit entry on the unknown-tokenizer path per FR-012. |
| `validate_credentials` | `async def validate_credentials(self, api_key: str, model: str) -> ValidationResult` | Lightweight credential check (e.g., a `models.list` ping for OpenAI-style providers); adapter chooses the cheapest verification call available. |
| `capabilities` | `def capabilities(self, model: str) -> Capabilities` | Model-static capability lookup. Per-process per-model cache per [research.md §3](./research.md). Specs 015/016/017/018 consume this. |
| `normalize_error` | `def normalize_error(self, exc: BaseException) -> CanonicalError` | Maps a provider-native exception to the canonical seven-category enumeration per FR-008. Constant-time per V14 budget 2. Spec 015 circuit breaker consumes this. |

Lifetime: instantiated once during FastAPI startup via `initialize_adapter()` per [research.md §5](./research.md); held in a module-level slot in `src/api_bridge/adapter.py`; method calls fan out from `get_adapter()` for the process lifetime.

## Process-scope registry

### `AdapterRegistry`

Maps env-var values to adapter classes. Read-only after orchestrator startup per FR-003.

| Method | Purpose |
|---|---|
| `register(name: str, cls: type[ProviderAdapter]) -> None` | Called from each adapter package's `__init__.py` at module-import time. Registers the name → class mapping. Raises `ValueError` if the name is already registered. |
| `get(name: str) -> type[ProviderAdapter] \| None` | Lookup by env-var value. Returns `None` for unregistered names; `initialize_adapter()` converts that to a `SystemExit` per V16 fail-closed. |
| `names() -> list[str]` | Returns sorted list of registered adapter names. Used by `initialize_adapter()` to format the error message when an invalid value is supplied. |

Internal state: `_REGISTRY: dict[str, type[ProviderAdapter]]` (module-level dict in `src/api_bridge/adapter.py`).

Lifetime: populated at adapter-package import time (orchestrator startup imports `src.api_bridge.litellm` and `src.api_bridge.mock`); read by `initialize_adapter()` once; held read-only thereafter. No public mutation API after startup.

## Frozen dataclasses at the adapter boundary

### `ProviderRequest`

Inbound payload to every adapter method. Carries everything an adapter needs to dispatch, without leaking orchestrator internals.

| Field | Type | Notes |
|---|---|---|
| `model` | `str` | Provider model identifier (e.g., `"claude-3-sonnet-20240229"`, `"gpt-4o"`). |
| `messages` | `list[dict[str, Any]]` | Assembled per-participant messages in OpenAI-shape; `format.py` produces this. Adapter translates to provider-native shape internally. |
| `api_key_encrypted` | `str \| None` | Encrypted at rest; adapter decrypts at dispatch moment, discards plaintext immediately per Constitution §3 (API key isolation). |
| `encryption_key` | `str` | Decryption key for `api_key_encrypted`. |
| `api_base` | `str \| None` | Provider endpoint override (e.g., self-hosted Ollama URL). |
| `timeout` | `int` | Per-attempt timeout seconds. |
| `max_tokens` | `int \| None` | Provider `max_tokens` cap. |
| `cache_directives` | `CacheDirectives \| None` | Generic cache-breakpoint directive per FR-010; adapter translates to provider-native syntax. From existing `src/api_bridge/caching.py`. |
| `provider_specific` | `dict[str, Any] \| None` | Opaque pass-through hook per spec assumption — unused by `LiteLLMAdapter` in v1; reserved for future provider-specific extensions (Anthropic prompt-caching quirks, OpenAI structured-outputs). |

Lifetime: created at the dispatch call site in `src/orchestrator/loop.py`; passed to the adapter; not persisted.

### `ProviderResponse`

Outbound payload from every dispatch call. Existing type from `src/orchestrator/types.py`; relocates to `src/api_bridge/adapter.py` (canonical home) per the plan's structure decision. The relocation is a re-export — existing import sites (`from src.orchestrator.types import ProviderResponse`) continue to work via a re-export shim.

| Field | Type | Notes |
|---|---|---|
| `model` | `str` | The model that produced the response. |
| `content` | `str` | Generated text. |
| `input_tokens` | `int` | Inbound tokens; from adapter's parse of provider response. |
| `output_tokens` | `int` | Outbound tokens; from adapter's parse of provider response. |
| `cost_usd` | `float` | Per-call cost in USD; the adapter writes `0.0` when it cannot compute (e.g., self-hosted Ollama). |
| `latency_ms` | `int` | Wall-clock latency from dispatch start to response receipt. |

Field names match the pre-feature `src/orchestrator/types.py` definition exactly (FR-014 byte-identical regression). The mock fixture parser also accepts the alias names `prompt_tokens` / `completion_tokens` / `cost` for fixture-author convenience; both shapes resolve to the same canonical fields.

`provider_family` and `finish_reason` are NOT on `ProviderResponse` in v1 — `provider_family` lives on `Capabilities` (queried separately via `adapter.capabilities(model)`) and `finish_reason` surfaces only on streaming `StreamEvent`s with `event_type=FINALIZATION`. Future amendment may promote one or both onto `ProviderResponse`.

Lifetime: returned from adapter call; consumed by orchestrator's per-turn loop; persisted to `messages` and `routing_log` via existing repositories.

### `Capabilities`

Returned by `capabilities(model)`. Spec 015/016/017/018 consume this for behavior gated on model capability.

| Field | Type | Notes |
|---|---|---|
| `supports_streaming` | `bool` | Whether the model supports streaming responses. |
| `supports_tool_calling` | `bool` | Native function-calling support. Spec 018 routes to `[NEED:]` proxy when `false`. |
| `supports_prompt_caching` | `bool` | Provider-native prompt caching availability. Spec 017 freshness logic gates on this. |
| `max_context_tokens` | `int` | Maximum input-token budget. Spec 018 deferred-loading consults this. |
| `tokenizer_name` | `str` | Tokenizer family identifier (e.g., `"cl100k_base"`, `"claude-3"`, `"llama3"`). |
| `recommended_temperature_range` | `tuple[float, float]` | `(min, max)` recommended temperature for the model. |
| `provider_family` | `str` | Bounded enum value (`"anthropic"`, `"openai"`, `"gemini"`, `"groq"`, `"ollama"`, `"vllm"`, `"unknown"`, or `"mock"`) per [research.md §12](./research.md). |

Lifetime: cached per-model per-process per [research.md §3](./research.md).

### `CanonicalError`

Returned by `normalize_error(exc)`. Spec 015's circuit breaker consumes only this (never the raw exception).

| Field | Type | Notes |
|---|---|---|
| `category` | `CanonicalErrorCategory` | Seven-value enum matching spec 015 §FR-003: `error_5xx`, `error_4xx`, `auth_error`, `rate_limit`, `timeout`, `quality_failure`, `unknown`. |
| `retry_after_seconds` | `int \| None` | Populated for `RATE_LIMIT` when provider supplies `Retry-After` header. `None` otherwise. |
| `original_exception` | `BaseException \| None` | Log-only; never re-raised. Routed to `routing_log` for forensic detail. |
| `provider_message` | `str \| None` | Provider's free-form error string for human-readable detail. |

Lifetime: created on every dispatch failure; consumed by spec 015's breaker and `routing_log`; not persisted as a row.

### `StreamEvent`

Yielded by `stream(request)`. Single SACP-internal event shape covering all provider-native streaming formats per FR-009.

| Field | Type | Notes |
|---|---|---|
| `event_type` | `StreamEventType` | Three-value enum: `text_delta`, `tool_call_delta`, `finalization`. |
| `content` | `str \| None` | Populated on `TEXT_DELTA`. |
| `tool_call` | `dict \| None` | Populated on `TOOL_CALL_DELTA`. Shape: `{"id": str, "name": str, "arguments": dict \| str}`. |
| `finish_reason` | `str \| None` | Populated on `FINALIZATION`. Provider's finish reason. |
| `usage` | `dict \| None` | Populated on `FINALIZATION`. Shape: `{"prompt_tokens": int, "completion_tokens": int}` — these are the LiteLLM streaming chunk's native field names, preserved as-is on the wire and only normalized to the `ProviderResponse` field names (`input_tokens` / `output_tokens`) in the non-streaming dispatch path. |

Lifetime: streamed from adapter to orchestrator's split-stream accumulator (sacp-design.md §6.5); consumed and discarded.

## Mock-only entities

### `MockFixtureSet`

Loaded from `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` per [research.md §7](./research.md). Frozen at load time; immutable thereafter.

| Field | Type | Notes |
|---|---|---|
| `responses` | `tuple[ResponseFixture, ...]` | Match-rule + response payload + optional stream-event sequence. |
| `errors` | `tuple[ErrorFixture, ...]` | Match-rule + canonical category + optional retry-after. |
| `capabilities` | `dict[str, Capabilities]` | Named capability sets (default `"default"`). |

### `ResponseFixture`

| Field | Type | Notes |
|---|---|---|
| `match_mode` | `Literal["hash", "substring"]` | Per [research.md §8](./research.md). |
| `match_value` | `str` | Sha256 hex (hash mode) or substring text (substring mode). |
| `response` | `ProviderResponse` | The fixture-canned response. |
| `stream_events` | `tuple[StreamEvent, ...] \| None` | Optional explicit stream sequence; default synthesized from `response.content`. |

### `ErrorFixture`

| Field | Type | Notes |
|---|---|---|
| `match_mode` | `Literal["hash", "substring"]` | Per [research.md §8](./research.md). |
| `match_value` | `str` | Sha256 hex or substring text. |
| `canonical_category` | `CanonicalErrorCategory` | The category to inject. |
| `retry_after_seconds` | `int \| None` | Populated for `rate_limit` fixtures. |
| `provider_message` | `str \| None` | Free-form detail. |

Lifetime: loaded once at adapter init via `MockAdapter.__init__`; held immutable until process exit.

## Module-level enumerations

### `CanonicalErrorCategory`

```python
class CanonicalErrorCategory(str, Enum):
    ERROR_5XX = "error_5xx"
    ERROR_4XX = "error_4xx"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    QUALITY_FAILURE = "quality_failure"
    UNKNOWN = "unknown"
```

Spec 015 §FR-003's enumeration; canonical home for the enum is `src/api_bridge/adapter.py`. Specs 015/016 import from here.

### `StreamEventType`

```python
class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    FINALIZATION = "finalization"
```

Per [research.md §1](./research.md). Canonical home in `src/api_bridge/adapter.py`.

## Relationships diagram (text form)

```
src/orchestrator/loop.py
        │
        │ get_adapter() → ProviderAdapter (process-singleton)
        ▼
+------------------------------------------------+
|  ProviderAdapter (ABC)                         |
|  +------------------+  +-------------------+   |
|  | LiteLLMAdapter   |  | MockAdapter       |   |
|  +------------------+  +-------------------+   |
+------------------------------------------------+
        │                       │
        ▼                       ▼
   provider call          fixture lookup
   (LiteLLM)              (MockFixtureSet)
        │                       │
        ▼                       ▼
   ProviderResponse        ProviderResponse
   StreamEvent stream      StreamEvent stream
   CanonicalError on fail  CanonicalError on fail (injected)
        │                       │
        ▼                       ▼
   src/orchestrator/circuit_breaker.py (consumes CanonicalError per FR-008)
   src/orchestrator/loop.py            (consumes ProviderResponse + StreamEvent stream)
   src/repositories/log_repo.py        (writes ProviderResponse fields to messages + routing_log)
   spec 016 metrics                    (reads provider_family + canonical category)
   spec 017 freshness                  (consults supports_prompt_caching)
   spec 018 deferred-loading           (consults max_context_tokens + count_tokens())
```

## State transitions

The adapter has a simple two-state lifecycle:

```
[uninitialized] --initialize_adapter()--> [active] --process exit--> [terminated]
```

`initialize_adapter()` is the single transition; calling it twice raises per [research.md §5](./research.md). `get_adapter()` requires `[active]`; calling in `[uninitialized]` raises. There is no `[active] → [uninitialized]` transition by design (FR-015 — mid-process adapter swap is OUT OF SCOPE).

## Validation rules

- `ProviderRequest.messages` MUST be a non-empty list (the orchestrator never dispatches an empty conversation). Adapter implementations MAY assume this.
- `ProviderRequest.timeout` MUST be a positive integer; values ≤ 0 are a programming error and trigger an assertion in the adapter's pre-dispatch validation.
- `Capabilities.max_context_tokens` MUST be ≥ 1024 (every supported provider family has at least this much; smaller values indicate a misconfigured fixture or a provider metadata bug).
- `Capabilities.recommended_temperature_range` MUST satisfy `0.0 ≤ min ≤ max ≤ 2.0`; out-of-range values surface as a fixture or model-metadata defect.
- `CanonicalError.retry_after_seconds`, when set, MUST be a non-negative integer (0 means "retry immediately"; negative values are nonsense).
- `MockFixtureSet.responses` and `errors` may be empty tuples (a fixture set that only configures capabilities is valid for capability-only tests).

## Cross-spec integration points (for /speckit.tasks)

- **Spec 015 circuit breaker**: consumes `CanonicalError` via `adapter.normalize_error(exc)` at every dispatch failure point. Tasks here ship the adapter side; spec 015's tasks (already shipped) gain a migration PR landed in this same single-PR cutover.
- **Spec 016 metrics**: consumes `Capabilities.provider_family` for the `provider_family` Prometheus label per [research.md §12](./research.md). No spec 016 task lands here; spec 016's tasks consume the field.
- **Spec 017 freshness**: consumes `Capabilities.supports_prompt_caching` to gate prompt-cache invalidation logic. The adapter normalizes provider-native cache-control directives per FR-010.
- **Spec 018 deferred-loading**: consumes `count_tokens()` and `Capabilities.max_context_tokens` as budget primitives. The adapter is the single source of truth for both.
