# Phase 0 Research: Pluggable Provider Adapter Abstraction

Resolves the twelve plan-time decisions queued in [plan.md](./plan.md). Spec-time clarifications (five items, resolved 2026-05-08) are NOT re-opened here — this document covers plan-time questions only.

## 1. `StreamEvent` shape

**Decision**: A frozen dataclass in `src/api_bridge/adapter.py`:

```python
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

**Rationale**:
- Frozen dataclass keeps every event immutable from creation — adapters cannot mutate events post-emission, so the orchestrator's split-stream accumulator (sacp-design.md §6.5) reads stable values.
- The three-event taxonomy matches FR-009 exactly. Anthropic's `content_block_delta` events become `TEXT_DELTA` (text fragments) or `TOOL_CALL_DELTA` (`input_json_delta` for tool args); Anthropic's `message_delta` + `message_stop` collapse into a single SACP `FINALIZATION` event with `finish_reason` and `usage` populated. OpenAI's `delta.content` becomes `TEXT_DELTA`; `delta.tool_calls[*]` becomes `TOOL_CALL_DELTA`; the chunk with `finish_reason != null` becomes `FINALIZATION`. No information loss in either direction.
- `tool_call: dict | None` is intentionally untyped at the dataclass level — the dict shape mirrors the orchestrator's existing tool-call internal format (`{"id": str, "name": str, "arguments": dict | str}`) so the adapter does the translation work, not the orchestrator.
- Buffering for out-of-causal-order provider events (spec edge case) happens inside the adapter; the orchestrator only sees the reordered SACP event stream.

**Alternatives considered**:
- Separate event classes per type (`TextDeltaEvent`, `ToolCallDeltaEvent`, `FinalizationEvent`) — rejected. Three classes complicate the iterator type signature (`AsyncIterator[StreamEvent | TextDeltaEvent | ToolCallDeltaEvent]`) without operational benefit; the enum tag suffices for dispatch.
- Discriminated-union with tagged dict instead of dataclass — rejected. Dataclass with optional fields preserves field-name ergonomics and IDE autocomplete; tagged dicts force string-key access at every consumer.
- Drop the `usage` field on `FINALIZATION` (move to a separate completion object) — rejected. Bundling `usage` in the final stream event keeps the streaming and non-streaming response paths symmetric: both terminate with the same usage shape.

## 2. `CanonicalError` enumeration

**Decision**: A frozen dataclass in `src/api_bridge/adapter.py` matching spec 015 §FR-003 exactly:

```python
class CanonicalErrorCategory(str, Enum):
    ERROR_5XX = "error_5xx"
    ERROR_4XX = "error_4xx"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    QUALITY_FAILURE = "quality_failure"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class CanonicalError:
    category: CanonicalErrorCategory
    retry_after_seconds: int | None = None    # populated for RATE_LIMIT when provider returns Retry-After
    original_exception: BaseException | None = None  # log-only; never re-raised
    provider_message: str | None = None       # human-readable provider detail for routing_log
```

**Rationale**:
- The seven-value enum is the exact spec 015 §FR-003 enumeration (verified by reading spec 015's spec.md FR-003 in the planning session — this document doesn't restate the enumeration to avoid drift if 015 amends).
- `retry_after_seconds` is populated only for `RATE_LIMIT` when the provider supplies a `Retry-After` header (HTTP 429) or LiteLLM's parsed `RateLimitError.retry_after`. Other categories leave it `None`. Spec 015's circuit breaker reads this field to schedule the next dispatch.
- `original_exception` is retained for forensic logging in `routing_log` but MUST NEVER be re-raised — the breaker consumes only `category`, never the raw exception (spec FR-008). The field is type-hinted as `BaseException | None` rather than `Exception | None` so adapter implementations can also forward `KeyboardInterrupt` / `SystemExit` if they propagate through provider calls (rare, but possible during signal-driven shutdown).
- `provider_message` is the provider's free-form error string (e.g., `"Anthropic API: model is overloaded, please retry in a moment"`) for human-readable detail in `routing_log` rows. Bounded length validation happens at log-emit time (existing log scrubber pattern) — the adapter does no truncation.

**Alternatives considered**:
- Single `category: str` with no enum — rejected. Enum gives compile-time validation for spec 015's `match canonical.category:` patterns and prevents typo-divergence between adapters.
- `retry_after_seconds` as `float | None` — rejected. Provider `Retry-After` headers are integer seconds (RFC 7231 §7.1.3); using `int` matches the contract precisely without losing precision.
- Separate `CanonicalRateLimitError(CanonicalError)` subclass for the `retry_after_seconds` carrier — rejected. Field-on-base with `None` default keeps the `match` dispatch flat in spec 015's breaker code.

## 3. `Capabilities` shape

**Decision**: A frozen dataclass with per-process per-model caching:

```python
@dataclass(frozen=True)
class Capabilities:
    supports_streaming: bool
    supports_tool_calling: bool
    supports_prompt_caching: bool
    max_context_tokens: int
    tokenizer_name: str
    recommended_temperature_range: tuple[float, float]
    provider_family: str            # research §12: source for spec 016's Prometheus label
```

**Decision** (cache shape): each adapter holds a `dict[str, Capabilities]` keyed by model name, populated lazily on first `capabilities(model)` call, persisted for the process lifetime. Concurrent calls for the same model on first miss are tolerated (the dict-write is idempotent — both callers compute the same value). No invalidation API; capabilities are model-static within a process.

**Rationale**:
- Spec FR-011 enumerates six required fields; research adds `provider_family` per cross-spec coupling with spec 016's metrics labelset.
- Per-process caching: capabilities are static — Anthropic Claude 3 Sonnet's max context, tokenizer, and tool-calling support don't change while the orchestrator is up. Recomputing on each call wastes negligible work but adds a dispatch overhead that fires on every spec 015/016/017/018 capability query. A simple dict cache is sufficient; no LRU is needed since the model set is bounded by per-session participants (Phase 3 ceiling 5).
- Concurrent cache-miss tolerance: FastAPI's async event loop serializes concurrent calls onto the same coroutine, so the simple `if model not in self._cap_cache: self._cap_cache[model] = self._compute_capabilities(model)` pattern is safe without a lock. (Mock adapter and LiteLLM adapter both compute capabilities synchronously — no awaitable in the hot path.)
- `tuple[float, float]` for temperature range gives consumers `(min, max)` semantics without unpacking ambiguity. Specs that gate on temperature (none in v1) get a typed bound.

**Alternatives considered**:
- Recompute on every call — rejected. Spec 016's per-turn metric emission would multiply the dispatch count.
- Pre-warm the cache for all six provider families at adapter init — rejected. The model set per process is tiny (≤5 distinct models per session); lazy population is simpler.
- `provider_family` as enum rather than string — rejected. Spec 016's bounded-enum requirement (FR-005) lives in spec 016's code; the adapter exposes a string and lets the consumer validate. This avoids cross-spec enum import cycles.

## 4. Adapter registration mechanism

**Decision**: Explicit registration in each adapter's `__init__.py`:

```python
# src/api_bridge/litellm/__init__.py
from src.api_bridge.adapter import AdapterRegistry
from src.api_bridge.litellm.adapter import LiteLLMAdapter

AdapterRegistry.register("litellm", LiteLLMAdapter)
```

```python
# src/api_bridge/mock/__init__.py
from src.api_bridge.adapter import AdapterRegistry
from src.api_bridge.mock.adapter import MockAdapter

AdapterRegistry.register("mock", MockAdapter)
```

The orchestrator's startup hook imports both packages (`import src.api_bridge.litellm  # noqa: F401`, `import src.api_bridge.mock  # noqa: F401`) before reading `SACP_PROVIDER_ADAPTER`, populating the registry. `get_adapter()` then reads the env var, looks up the class, and instantiates.

**Rationale**:
- Explicit `register()` calls in `__init__.py` are immediately greppable — finding what's registered with what name is a single `grep -rn "AdapterRegistry.register"` away. Decorator-based registration buries the registration site in the class definition file, which is fine for one adapter but obscures the registry's contents at a glance.
- No hidden state: the registry is populated only by explicit imports + explicit `register()` calls. Orchestrator startup imports both packages deterministically; no module-level magic.
- Future adapters add their own `__init__.py` registration; the orchestrator's startup adds an `import src.api_bridge.<name>  # noqa: F401` line. Adding an adapter is a two-touch change (registration + import) — slightly more verbose than a one-touch decorator, but the explicitness is worth the line.

**Alternatives considered**:
- Decorator-based registration (`@AdapterRegistry.register("litellm")` on the class) — rejected. The decorator imports the registry, the registry doesn't import the adapter — fine for a single side, but combined with the explicit-import-in-startup pattern needed to populate the registry anyway, the decorator buys no real conciseness.
- Entry-points (setuptools `entry_points`) for plugin-style discovery — rejected. Overkill for the v1 in-tree adapter set; entry-points add packaging complexity and obscure the registry contents from grep. Phase 3+ may revisit if external adapter packages become a thing.
- Module-import-side-effect registration without explicit `__init__.py` — rejected. Side-effect imports are a known footgun; CI's `unused-imports` checker would have to be carved out for the noqa lines, which is a smell.

## 5. `get_adapter()` factory and process-scope singleton

**Decision**: Module-level slot in `src/api_bridge/adapter.py`:

```python
_ACTIVE_ADAPTER: ProviderAdapter | None = None

def initialize_adapter() -> None:
    """Called once during FastAPI startup; reads env var, instantiates adapter."""
    global _ACTIVE_ADAPTER
    if _ACTIVE_ADAPTER is not None:
        raise RuntimeError("Adapter already initialized; mid-process swap is OUT OF SCOPE per spec 020 FR-015.")
    name = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm")
    cls = AdapterRegistry.get(name)
    if cls is None:
        raise SystemExit(
            f"SACP_PROVIDER_ADAPTER={name!r} is not registered. "
            f"Registered adapters: {sorted(AdapterRegistry.names())}"
        )
    _ACTIVE_ADAPTER = cls()

def get_adapter() -> ProviderAdapter:
    """Return the process-scope active adapter."""
    if _ACTIVE_ADAPTER is None:
        raise RuntimeError("Adapter not initialized. Call initialize_adapter() during startup.")
    return _ACTIVE_ADAPTER
```

The orchestrator's `lifespan` async context manager calls `initialize_adapter()` after env-var validation and before the FastAPI router accepts connections. `get_adapter()` is the read path; it never awaits and never re-instantiates.

**Rationale**:
- Module-level slot is simple, single-process, single-threaded-init-safe (FastAPI's `lifespan` startup hook is awaited synchronously before traffic accepts). The double-init guard catches accidental re-init paths during test setup.
- `SystemExit` (not `RuntimeError`) on invalid env var name — V15/V16 fail-closed contract: invalid configuration MUST exit, not raise an internal exception that gets caught by FastAPI's error middleware.
- `AdapterRegistry.names()` returns a sorted list of registered names so the error message lists registered adapters deterministically — operators reading the error see exactly what's available.
- `get_adapter()` is callable from sync code (e.g., orchestrator helpers that run outside async contexts); never marked `async def`. The adapter's *methods* are async (`dispatch`, `stream`); the factory is not.

**Alternatives considered**:
- Class-based `AdapterManager` singleton — rejected. Module-level slot is simpler and Python's import system already provides singleton-like semantics for module state.
- Lazy initialization on first `get_adapter()` call — rejected. V15/V16 says startup-time validation; if the env var is wrong, the orchestrator MUST exit before binding ports, not on first dispatch.
- Threading.Lock around the init slot — rejected. FastAPI startup is single-threaded; introducing a lock signals concurrency support that isn't there per FR-002.

## 6. LiteLLM exception-to-canonical mapping table

**Decision**: A static mapping table in `src/api_bridge/litellm/errors.py` covering LiteLLM's documented exception hierarchy:

| LiteLLM exception class | Canonical category | Rationale |
|---|---|---|
| `litellm.AuthenticationError` | `AUTH_ERROR` | API key invalid, expired, or insufficient permissions. |
| `litellm.PermissionDeniedError` | `AUTH_ERROR` | Same trust boundary as auth — separate category not justified. |
| `litellm.RateLimitError` | `RATE_LIMIT` | Provider 429. `retry_after_seconds` populated from `exc.retry_after` when present. |
| `litellm.Timeout` | `TIMEOUT` | LiteLLM's wrapper for asyncio.TimeoutError on provider calls. |
| `litellm.APIConnectionError` | `TIMEOUT` | Connection-level failures; treated as transient timeouts for breaker purposes. |
| `litellm.ContextWindowExceededError` | `ERROR_4XX` | Request shape failure (prompt too long for model); not generation quality. Caller can re-prompt with shorter context. |
| `litellm.BadRequestError` | `ERROR_4XX` | Generic 400; malformed request payload. |
| `litellm.UnprocessableEntityError` | `ERROR_4XX` | 422; payload-validation failure. |
| `litellm.NotFoundError` | `ERROR_4XX` | 404; model name unknown to provider. |
| `litellm.ContentPolicyViolationError` | `QUALITY_FAILURE` | Provider refused to generate; treated as quality failure for breaker semantics. |
| `litellm.ServiceUnavailableError` | `ERROR_5XX` | 503; provider-side transient. |
| `litellm.InternalServerError` | `ERROR_5XX` | 500; provider-side. |
| `litellm.APIError` (base, status code unknown) | `UNKNOWN` | Fallback when no specific class matched. |
| Any other `Exception` | `UNKNOWN` | Last-resort fallback. Logged with full traceback in `routing_log`. |

The mapping is implemented as:

```python
def _normalize_litellm_error(exc: BaseException) -> CanonicalError:
    if isinstance(exc, litellm.RateLimitError):
        retry_after = getattr(exc, "retry_after", None)
        return CanonicalError(category=CanonicalErrorCategory.RATE_LIMIT,
                              retry_after_seconds=retry_after,
                              original_exception=exc,
                              provider_message=str(exc))
    if isinstance(exc, litellm.AuthenticationError | litellm.PermissionDeniedError):
        return CanonicalError(category=CanonicalErrorCategory.AUTH_ERROR, ...)
    # ... etc for each category
    return CanonicalError(category=CanonicalErrorCategory.UNKNOWN,
                          original_exception=exc,
                          provider_message=str(exc))
```

**Rationale**:
- Maps every documented LiteLLM exception class to a canonical category with a stated rationale per row. Spec 015's circuit breaker depends on stable category assignment; this table is the contract.
- `ContextWindowExceededError → ERROR_4XX` (not `QUALITY_FAILURE`) because the failure is a request-shape problem (prompt too long), not a generation-quality problem. The breaker should not trip on an oversized prompt; the orchestrator's context assembly should re-trim and retry.
- `APIConnectionError → TIMEOUT` (not `ERROR_5XX`) because connection-level failures are transient infrastructure issues — the breaker treats them like timeouts for retry-with-backoff semantics.
- `ContentPolicyViolationError → QUALITY_FAILURE` because the provider's content filter judged the output unacceptable; this is the canonical "quality failure" category in spec 015's enumeration.
- The fallback `UNKNOWN` category is logged with full traceback so operators can identify any LiteLLM exception class the table missed (and amend the mapping in a follow-up PR).

**Alternatives considered**:
- Map by HTTP status code rather than class name — rejected. LiteLLM's exception classes carry semantic intent that status codes don't — `ContentPolicyViolationError` and `BadRequestError` may share status code 400 but differ in canonical category.
- Catch-all `except Exception → UNKNOWN` without per-class branches — rejected. Spec 015's breaker needs distinct categories to apply different cooldown/retry semantics; collapsing to UNKNOWN defeats the purpose.

## 7. Mock-adapter fixture format

**Decision**: JSON, with a top-level dict shape:

```json
{
  "responses": [
    {
      "match": {"mode": "hash", "value": "<sha256-hex-of-canonical-message-list>"},
      "response": {
        "content": "hello world",
        "prompt_tokens": 42,
        "completion_tokens": 10,
        "model": "mock-model",
        "finish_reason": "stop",
        "cost": 0.0
      },
      "stream_events": [
        {"event_type": "text_delta", "content": "hello "},
        {"event_type": "text_delta", "content": "world"},
        {"event_type": "finalization", "finish_reason": "stop", "usage": {"prompt_tokens": 42, "completion_tokens": 10}}
      ]
    },
    {
      "match": {"mode": "substring", "value": "explain the algorithm"},
      "response": {
        "content": "...",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "model": "mock-model",
        "finish_reason": "stop",
        "cost": 0.0
      }
    }
  ],
  "errors": [
    {
      "match": {"mode": "substring", "value": "trigger 5xx"},
      "canonical_category": "error_5xx",
      "retry_after_seconds": null,
      "provider_message": "mock provider unavailable"
    },
    {
      "match": {"mode": "substring", "value": "trigger rate limit"},
      "canonical_category": "rate_limit",
      "retry_after_seconds": 30,
      "provider_message": "mock rate limit"
    }
  ],
  "capabilities": {
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
}
```

**Rationale**:
- JSON: existing `tests/fixtures/` precedent uses JSON; the orchestrator's existing `json` standard-library import covers parsing without a new dep. YAML's `yaml` package would add a runtime dependency — non-trivial because the mock adapter is part of the runtime (selectable via env var for staging/dev environments), not just test code.
- Top-level `responses` + `errors` + `capabilities` keys match the three orthogonal mock-adapter capabilities: deterministic dispatch, injectable error modes, fixture-controllable capability negotiation (per spec acceptance scenario 4 of US2).
- Match-key shape carries `mode` ("hash" | "substring") and `value` (sha256 hex or substring text). Hash mode gives byte-identical fixture replay; substring mode gives ergonomic test-writing without computing canonical hashes.
- `stream_events` is optional per response — when present, mock streaming returns the listed events in order; when absent, a default three-event sequence is synthesized from the `response.content` (single TEXT_DELTA + FINALIZATION).
- `capabilities` keyed by name (not model — model→name mapping is a fixture-set decision); the mock adapter's `capabilities(model)` looks up the configured name (default `"default"`) per fixture-test scenario.

**Alternatives considered**:
- YAML — rejected per dependency cost above.
- Python-source fixtures (importable Python files defining fixture objects) — rejected. Mock fixtures are data, not code; JSON keeps them inert.
- TOML — rejected. JSON is the established repo convention; introducing TOML for one fixture format adds tool/parser fragmentation.

## 8. Fixture input matching

**Decision**: Two match modes, `hash` and `substring`, with hash tried first:

```python
def _match_fixture(messages: list[dict], fixtures: list[FixtureEntry]) -> FixtureEntry | None:
    canonical = _canonical_message_hash(messages)  # sha256(json.dumps(messages, sort_keys=True))
    for entry in fixtures:
        if entry.match_mode == "hash" and entry.match_value == canonical:
            return entry
    last_text = messages[-1].get("content", "") if messages else ""
    for entry in fixtures:
        if entry.match_mode == "substring" and entry.match_value in last_text:
            return entry
    return None  # no match — `MockAdapter` raises `MockFixtureMissing` per FR-007
```

The canonical hash is sha256 over `json.dumps(messages, sort_keys=True, ensure_ascii=False)` — sorted keys for determinism, no ASCII escaping for unicode-safe matching.

**Rationale**:
- Hash-first preserves exact-replay semantics for tests that need byte-identical fixture matching (e.g., regression tests for spec 015 breaker behavior on a specific message sequence).
- Substring fallback allows ergonomic test-writing — a test can write `match: "trigger 5xx"` without computing a hash, and the fixture fires whenever the last message contains that substring.
- Hash-first ordering means a hash match always wins over a substring match — tests that need precise control can hash; tests that want loose matching can substring. No order-of-fixtures sensitivity within a single mode (first hash match wins; first substring match wins).
- `MockFixtureMissing` is raised when no entry matches — never silently return a default per FR-007.

**Alternatives considered**:
- Substring-only — rejected. Some tests need exact replay; substring matching is fragile when message content overlaps across fixtures.
- Regex match mode — deferred. Three modes (hash, substring, regex) is more surface than v1 needs; regex can land in a follow-up if a test requires it.
- Match against full message-list text concatenation rather than just last-message — rejected. The last-message convention matches how facilitator/participant tests author input — the fixture's intent is to control the response to *this* turn's prompt.

## 9. Cross-validator dependency between the two new env vars

**Decision**: A single `validate_provider_adapter_mock_fixtures_path` validator that reads `SACP_PROVIDER_ADAPTER` first and applies its rules conditionally — mirroring spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` precedent:

```python
def validate_provider_adapter_mock_fixtures_path() -> None:
    adapter = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm").lower()
    path = os.environ.get("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH")
    if adapter == "mock":
        if not path:
            raise ConfigError("SACP_PROVIDER_ADAPTER=mock requires SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH to be set")
        if not os.path.isfile(path):
            raise ConfigError(f"SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH={path!r} is not a readable file")
        try:
            with open(path) as f:
                json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH={path!r} contains invalid JSON: {e}")
    # When adapter != "mock", the path var is ignored — no validation runs.

def validate_provider_adapter() -> None:
    name = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm").lower()
    valid = {"litellm", "mock"}  # extended as future adapters register
    if name not in valid:
        raise ConfigError(f"SACP_PROVIDER_ADAPTER={name!r} not in registered adapter names: {sorted(valid)}")
```

Both validators land in `src/config/validators.py` and register in the `VALIDATORS` tuple. Validation order is deterministic (tuple iteration); the registry's runtime `AdapterRegistry.names()` gives the same `valid` set the validator checks against, but the validator hardcodes the v1 set to keep startup-validation simple (the registry isn't populated until imports run, but validators run before imports — so the validator hardcodes; future adapters extend the set).

**Rationale**:
- Cross-validator pattern mirrors spec 014's existing precedent (`SACP_AUTO_MODE_ENABLED=true` requires `SACP_DMA_DWELL_TIME_S` set). Operators reading the validators see a consistent shape.
- Hardcoding `valid = {"litellm", "mock"}` in the validator is intentional — startup validation runs before adapter packages import (which would populate the registry); the validator is the early gate. When a future adapter lands, its spec amends this validator to add the new name.
- JSON parse-check happens at validator time so unparseable fixture files are caught BEFORE the orchestrator binds ports per V16 fail-closed.
- File-readability check (`os.path.isfile`) is the V16-mandated sanity check; deeper schema validation happens at adapter instantiation time, not validator time, since schema validation requires the adapter package to be loaded.

**Alternatives considered**:
- Two independent validators with no cross-check, relying on adapter-init failure to surface the dependency — rejected. V16 mandates startup validation; deferring to adapter-init means the failure happens after port-binding, which violates fail-closed.
- A single combined validator for both vars — rejected. The two vars have distinct concerns (adapter name registry membership vs. fixture file readability); combining them obscures the failure mode in error messages.

## 10. Topology-7 forward note

**Decision**: Adapter-init code checks `SACP_TOPOLOGY` env var and skips registry instantiation when it equals `"7"`:

```python
def initialize_adapter() -> None:
    topology = os.environ.get("SACP_TOPOLOGY", "1")
    if topology == "7":
        log.info("Topology 7 (MCP-to-MCP) active; provider adapter not initialized.")
        return  # No bridge layer; orchestrator becomes a state manager.
    # ... normal initialization path
```

`get_adapter()` raises a clear error when called in topology 7 ("topology 7 has no bridge layer; this code path should not execute") — same gate-pattern as specs 014/021 §V12.

**Rationale**:
- Same forward-document pattern as specs 014/021. The gate is a one-line check that costs nothing in topology 1-6 and prevents the adapter from initializing when topology 7 is active.
- Clear error message on `get_adapter()` in topology 7 helps surface dispatch-path code that hasn't been topology-aware-ed; future Phase 3+ work for topology 7 will shape these gates more precisely.
- `SACP_TOPOLOGY` validator (existing per spec 011 / sacp-design.md) is the single source of truth; this code reads it at adapter-init time only.

**Alternatives considered**:
- Implement a `NoOpAdapter` for topology 7 — rejected. Topology 7 has no bridge layer at all; a no-op adapter implies dispatch happens, which is wrong. The skip-init + raise-on-call approach is correct.
- Move the topology check into the registry rather than the init path — rejected. The registry should be topology-agnostic; topology gating is a runtime concern.

## 11. Spec 015 circuit-breaker integration point

**Decision**: Replace exception-class catches in `src/orchestrator/circuit_breaker.py` with a generic `except Exception as exc` followed by `canonical = adapter.normalize_error(exc)`, dispatching on `canonical.category`:

```python
# Before (current code)
try:
    response = await dispatch_with_retry(...)
except litellm.RateLimitError as exc:
    breaker.record_failure(participant_id, kind="rate_limit", retry_after=exc.retry_after)
    raise
except litellm.AuthenticationError as exc:
    breaker.record_failure(participant_id, kind="auth_error")
    raise
# ... etc

# After (post-refactor)
try:
    response = await adapter.dispatch_with_retry(...)
except Exception as exc:
    canonical = adapter.normalize_error(exc)
    breaker.record_failure(participant_id,
                           kind=canonical.category.value,
                           retry_after=canonical.retry_after_seconds)
    raise  # re-raise the original exception unchanged
```

The `kind=` parameter on `breaker.record_failure` accepts the canonical category string per spec 015 §FR-003's enumeration. Spec 015's tests are amended to use canonical categories; the breaker's per-category cooldown logic is unchanged.

**Rationale**:
- Single integration point: the dispatch-with-retry call site in `circuit_breaker.py` (and any other dispatch-path call sites) becomes provider-library-agnostic.
- Re-raising the original exception preserves the existing error-propagation contract — callers that want to handle specific categories can read `canonical.category` from the breaker's record, but the raised exception remains the LiteLLM (or future-adapter) original. This minimizes ripple.
- Spec 015 tests gain a clean migration: tests that previously asserted `with pytest.raises(litellm.RateLimitError)` become `with pytest.raises(Exception) as exc_info: ...; canonical = adapter.normalize_error(exc_info.value); assert canonical.category == CanonicalErrorCategory.RATE_LIMIT`. The mock adapter (US2) makes these tests deterministic without network.

**Alternatives considered**:
- Have the adapter raise a `CanonicalErrorRaisedException(canonical)` instead of letting the original exception propagate — rejected. Wrapping changes the exception type at every call site; minimizing ripple means letting the original exception flow and using `normalize_error` only at decision points.
- Move the breaker's `record_failure` call into the adapter — rejected. The breaker is per-participant state; the adapter is process-wide. Coupling them violates separation of concerns.

## 12. `provider_family` label sourcing for spec 016 metrics

**Decision**: `Capabilities.provider_family` is the authoritative source for spec 016's Prometheus `provider_family` label. The LiteLLM adapter computes it from LiteLLM's `get_llm_provider(model)` helper, mapped to the bounded enum:

```python
_PROVIDER_FAMILY_MAP = {
    "anthropic": "anthropic",
    "openai": "openai",
    "azure": "openai",            # Azure OpenAI maps to openai family
    "vertex_ai": "gemini",        # Google Vertex maps to gemini family
    "gemini": "gemini",
    "groq": "groq",
    "ollama": "ollama",
    "vllm": "vllm",
    "together_ai": "openai",      # OpenAI-compatible endpoints map to openai
    "openrouter": "openai",       # OpenAI-compatible
    # ... extended as new providers appear
}

def _capabilities(model: str) -> Capabilities:
    raw_family, *_ = litellm.get_llm_provider(model)
    family = _PROVIDER_FAMILY_MAP.get(raw_family, "unknown")
    return Capabilities(..., provider_family=family)
```

The mock adapter's `provider_family` defaults to `"mock"` (configurable per fixture-set per research §7).

**Rationale**:
- Spec 016 §FR-005 requires a bounded enumeration for the `provider_family` label (Prometheus cardinality control). The mapping table converts LiteLLM's free-form provider names to the bounded enum.
- OpenAI-compatible endpoints (Azure, Together, OpenRouter) collapse into the `openai` family because their wire format is OpenAI-shaped and their behavior is interchangeable from the metrics observer's perspective.
- `unknown` fallback handles any future LiteLLM provider name not yet in the map; spec 016's metric continues to emit (with cardinality control), and a follow-up PR amends the map.

**Alternatives considered**:
- Source `provider_family` from a separate per-model config file — rejected. The adapter already knows the provider; central config would duplicate knowledge.
- Drop the bounded enum and emit raw LiteLLM provider names — rejected. Cardinality unbounded; spec 016 §FR-005 explicitly requires bounded enum.

---

**End of research.** All twelve plan-time decisions resolved. Ready for Phase 1 (data-model.md, contracts/, quickstart.md).
