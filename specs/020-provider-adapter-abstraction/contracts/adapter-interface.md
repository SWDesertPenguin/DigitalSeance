# Contract: ProviderAdapter interface

The sole boundary between the dispatch path and any underlying provider library. Every concrete adapter MUST implement this contract; no dispatch-path code outside `src/api_bridge/` may import provider-native types.

## Method signatures

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class ProviderAdapter(ABC):

    @abstractmethod
    async def dispatch(self, request: ProviderRequest) -> ProviderResponse:
        """Single non-streaming dispatch. Returns the assembled response.

        Raises any provider-native exception on failure; callers consume
        `normalize_error(exc)` to map to the canonical category.
        """

    @abstractmethod
    async def dispatch_with_retry(self, request: ProviderRequest) -> ProviderResponse:
        """Dispatch with provider-side retry per spec 003 FR-031 compound budget.

        Adapter encapsulates retry policy (backoff, jitter, retry-after honoring);
        orchestrator sets the budget via existing env vars (no new vars in this spec).
        """

    @abstractmethod
    def stream(self, request: ProviderRequest) -> AsyncIterator[StreamEvent]:
        """Streaming dispatch yielding SACP StreamEvents in causal order.

        Adapter buffers and reorders provider-native events when needed
        (per spec edge case "Streaming event order from the adapter does not
        match the orchestrator's expected sequence").
        """

    @abstractmethod
    def count_tokens(self, messages: list[dict], model: str) -> int:
        """Inbound token count using the participant's model tokenizer.

        Returns conservative-overestimate using a generic tokenizer when
        model is unknown, AND emits an audit entry on the unknown-tokenizer
        path per FR-012.
        """

    @abstractmethod
    async def validate_credentials(self, api_key: str, model: str) -> ValidationResult:
        """Lightweight credential check.

        Adapter chooses the cheapest verification call available
        (e.g., a `models.list` ping for OpenAI-style providers,
        an `/v1/messages` HEAD-style probe for Anthropic).
        """

    @abstractmethod
    def capabilities(self, model: str) -> Capabilities:
        """Model-static capability lookup.

        Per-process per-model cache (capabilities are static within a process).
        Specs 015/016/017/018 consult this for any behavior gated on model
        capability per FR-011.
        """

    @abstractmethod
    def normalize_error(self, exc: BaseException) -> CanonicalError:
        """Map a provider-native exception to canonical seven-category enum.

        Constant-time per V14 budget 2 (no I/O, no allocation beyond the
        returned CanonicalError object). Spec 015's circuit breaker consumes
        only the canonical category, never the raw exception per FR-008.
        """
```

## Lifecycle

1. **Module-import time**: each adapter package's `__init__.py` calls `AdapterRegistry.register(name, cls)` per [research.md §4](../research.md). The orchestrator's startup imports both packages to populate the registry.
2. **Startup**: FastAPI `lifespan` async context manager invokes `initialize_adapter()` from `src/api_bridge/adapter.py` AFTER env-var validation and BEFORE the FastAPI router accepts connections. `initialize_adapter()` reads `SACP_PROVIDER_ADAPTER`, looks up the class, and instantiates it. Stores the instance in `_ACTIVE_ADAPTER` (module-level slot).
3. **Runtime**: every dispatch-path call site calls `get_adapter()` to retrieve the singleton. The adapter's methods are awaited per their signatures. No mid-process re-init API exposed (FR-015 — mid-process adapter swap is OUT OF SCOPE).
4. **Process exit**: adapter has no shutdown protocol in v1; provider connections are HTTP-level and close on process termination. Future adapters with persistent connections may add a `close()` method in a follow-up spec.

## Registry semantics

```python
class AdapterRegistry:
    _REGISTRY: dict[str, type[ProviderAdapter]] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type[ProviderAdapter]) -> None:
        if name in cls._REGISTRY:
            raise ValueError(f"Adapter {name!r} already registered")
        cls._REGISTRY[name] = adapter_cls

    @classmethod
    def get(cls, name: str) -> type[ProviderAdapter] | None:
        return cls._REGISTRY.get(name)

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._REGISTRY.keys())
```

- Read-only after orchestrator startup per FR-003 (no public mutation API after the import-time registration phase).
- Duplicate registration raises immediately; this is a programming error, not a runtime configuration concern.
- `get(name)` returns `None` for unregistered names; `initialize_adapter()` converts that to a `SystemExit` with a clear error per V16 fail-closed.

## Capability cache

```python
class LiteLLMAdapter(ProviderAdapter):
    def __init__(self) -> None:
        self._cap_cache: dict[str, Capabilities] = {}

    def capabilities(self, model: str) -> Capabilities:
        if model not in self._cap_cache:
            self._cap_cache[model] = self._compute_capabilities(model)
        return self._cap_cache[model]
```

Per [research.md §3](../research.md): per-process per-model lazy cache; concurrent-cache-miss-tolerance via FastAPI's single-threaded async event loop; no LRU because the model set is bounded (Phase 3 ceiling 5 participants per session).

## `provider_family` field

Every adapter's `Capabilities.provider_family` MUST return one of the bounded enum values: `"anthropic"`, `"openai"`, `"gemini"`, `"groq"`, `"ollama"`, `"vllm"`, `"unknown"`, or `"mock"` (mock-only). Per [research.md §12](../research.md), spec 016's Prometheus `provider_family` label sources from this field directly — cardinality control depends on the bounded enum.

LiteLLM adapter computes the value via the mapping in [research.md §12](../research.md) using `litellm.get_llm_provider(model)`; mock adapter returns `"mock"` by default (configurable per fixture-set per `contracts/mock-fixtures.md`).

## Topology gating

Per [research.md §10](../research.md), `initialize_adapter()` checks `SACP_TOPOLOGY` and returns early without instantiating any adapter when the value is `"7"` (MCP-to-MCP topology; orchestrator becomes a state manager with no bridge layer). `get_adapter()` raises a clear error when called in topology 7. This is the same forward-document pattern used in specs 014/021 §V12.

## Cross-spec coupling

| Consumer | Consumed surface | Purpose |
|---|---|---|
| spec 015 circuit breaker | `normalize_error(exc)` returning `CanonicalError` | Per-category cooldown / retry semantics. The breaker MUST consume only `canonical.category`; never the raw exception. |
| spec 016 Prometheus metrics | `Capabilities.provider_family` | Bounded `provider_family` label (FR-005 cardinality control). |
| spec 017 tool-list freshness | `Capabilities.supports_prompt_caching` + cache-control normalization (FR-010) | Gate prompt-cache-invalidation logic on whether the provider actually supports prompt caching. |
| spec 018 deferred tool loading | `count_tokens()` + `Capabilities.max_context_tokens` | Budget primitive for partition policy. |
| spec 002 mcp-server | `validate_credentials(api_key, model)` | Participant registration validates credentials at submit time per FR-001. |
| orchestrator dispatch loop | `dispatch_with_retry(request)` + `stream(request)` | Replaces every direct LiteLLM import in the hot path per FR-005. |

## Migration contract for the single-PR cutover (clarification 2026-05-08)

Every consumer of `from src.api_bridge.provider import dispatch_with_retry` migrates to:

```python
from src.api_bridge.adapter import get_adapter

# at startup (one-time):
initialize_adapter()  # called from FastAPI lifespan

# at dispatch call site:
adapter = get_adapter()
response = await adapter.dispatch_with_retry(ProviderRequest(...))
```

Every consumer of `except litellm.RateLimitError` (or any other `litellm.*Error`) migrates to:

```python
try:
    response = await adapter.dispatch_with_retry(...)
except Exception as exc:
    canonical = adapter.normalize_error(exc)
    if canonical.category == CanonicalErrorCategory.RATE_LIMIT:
        ...
    raise  # re-raise the original
```

The architectural test (`tests/test_020_no_litellm_imports.py`) enforces that no `import litellm` / `from litellm` line remains anywhere in `src/` outside `src/api_bridge/litellm/`. Test fails the build if violated.
