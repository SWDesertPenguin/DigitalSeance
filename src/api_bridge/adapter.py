# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pluggable provider adapter abstraction (spec 020).

The sole boundary between the dispatch path and any underlying provider
library. Defines the `ProviderAdapter` ABC, canonical SACP-internal
types (`StreamEvent`, `CanonicalError`, `Capabilities`, `ProviderRequest`,
`ProviderResponse`), the process-scope `AdapterRegistry`, and the
`get_adapter()` / `initialize_adapter()` lifecycle functions.

Implementations register with `AdapterRegistry` at module-import time
per research.md §4. The orchestrator's FastAPI lifespan invokes
`initialize_adapter()` once at startup; `get_adapter()` returns the
process-scope singleton thereafter. Mid-process adapter swap is OUT OF
SCOPE per FR-015.

Per FR-005, no file under `src/` outside `src/api_bridge/litellm/` may
import `litellm`. The architectural test in
`tests/test_020_no_litellm_imports.py` enforces that constraint.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical enumerations
# ---------------------------------------------------------------------------


class CanonicalErrorCategory(StrEnum):
    """Seven-value canonical error taxonomy matching spec 015 §FR-003."""

    ERROR_5XX = "error_5xx"
    ERROR_4XX = "error_4xx"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    QUALITY_FAILURE = "quality_failure"
    UNKNOWN = "unknown"


class StreamEventType(StrEnum):
    """Three-value SACP-internal streaming event taxonomy per FR-009."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    FINALIZATION = "finalization"


# ---------------------------------------------------------------------------
# Frozen dataclasses at the SACP <-> adapter boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """Single SACP-internal streaming event shape per FR-009."""

    event_type: StreamEventType
    content: str | None = None
    tool_call: dict[str, Any] | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CanonicalError:
    """Adapter-canonical error returned by `normalize_error(exc)`.

    Spec 015's circuit breaker consumes `category` and
    `retry_after_seconds`; never the raw exception per FR-008.
    """

    category: CanonicalErrorCategory
    retry_after_seconds: int | None = None
    original_exception: BaseException | None = None
    provider_message: str | None = None


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Model-static capability shape per FR-011 + research.md §3 / §12.

    Cached per-process per-model by each adapter implementation. Specs
    015/016/017/018 consume this for any behavior gated on model
    capability.
    """

    supports_streaming: bool
    supports_tool_calling: bool
    supports_prompt_caching: bool
    max_context_tokens: int
    tokenizer_name: str
    recommended_temperature_range: tuple[float, float]
    provider_family: str


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Inbound payload to every adapter dispatch method.

    Carries everything an adapter needs to dispatch without leaking
    orchestrator internals. The `provider_specific` field is an opaque
    pass-through for future provider-specific extensions; unused by the
    LiteLLM adapter in v1.
    """

    model: str
    messages: list[dict[str, Any]]
    api_key_encrypted: str | None
    encryption_key: str
    api_base: str | None = None
    timeout: int = 60
    max_tokens: int | None = None
    cache_directives: Any = None  # CacheDirectives — Any to avoid import cycle
    provider_specific: dict[str, Any] | None = None


# ProviderResponse is the canonical home for the existing dataclass that
# previously lived in src/orchestrator/types.py. We keep the field set
# (content, input_tokens, output_tokens, cost_usd, model, latency_ms)
# unchanged for FR-014 byte-identical regression behavior; downstream
# code that imports `from src.orchestrator.types import ProviderResponse`
# continues to work via a re-export shim in that module.
@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Outbound payload from every dispatch call.

    Field set preserved from the pre-feature `src/orchestrator/types.py`
    definition so FR-014 byte-identical regression holds. The data-model
    document refers to `prompt_tokens` / `completion_tokens` / `cost`;
    those are the same values the existing code names `input_tokens` /
    `output_tokens` / `cost_usd`. The names in this dataclass are
    authoritative for the codebase.
    """

    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    latency_ms: int
    # Spec 026 US1 — provider-side cache-hit signal. Populated by the
    # adapter when the dispatched provider returns a cache-hit indicator
    # (Anthropic ``usage.cache_read_input_tokens``, OpenAI
    # ``usage.prompt_tokens_details.cached_tokens``). ``None`` on
    # providers that do not surface a cache-hit marker; ``0`` on a
    # cache-miss; positive integer on a cache hit. The loop's
    # ``routing_log`` emission consumes this to record the FR-003
    # ``cache_hit`` / ``cache_miss`` marker.
    cached_prefix_tokens: int | None = None


# ---------------------------------------------------------------------------
# ValidationResult (used by validate_credentials)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of `adapter.validate_credentials(api_key, model)`."""

    ok: bool
    detail: str | None = None


# ---------------------------------------------------------------------------
# ProviderAdapter abstract base class
# ---------------------------------------------------------------------------


class ProviderAdapter(ABC):
    """Sole boundary between the dispatch path and any provider library.

    Concrete implementations (LiteLLMAdapter, MockAdapter) register with
    `AdapterRegistry` at module-import time. One adapter per orchestrator
    process; immutable for the process lifetime per FR-002.
    """

    @abstractmethod
    async def dispatch(self, request: ProviderRequest) -> ProviderResponse:
        """Single non-streaming dispatch."""

    @abstractmethod
    async def dispatch_with_retry(self, request: ProviderRequest) -> ProviderResponse:
        """Dispatch with provider-side retry per spec 003 FR-031 budget."""

    @abstractmethod
    def stream(self, request: ProviderRequest) -> AsyncIterator[StreamEvent]:
        """Streaming dispatch yielding SACP `StreamEvent`s in causal order."""

    @abstractmethod
    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        """Inbound token count using the participant's model tokenizer."""

    @abstractmethod
    async def validate_credentials(self, api_key: str, model: str) -> ValidationResult:
        """Lightweight credential check."""

    @abstractmethod
    def capabilities(self, model: str) -> Capabilities:
        """Model-static capability lookup with per-process per-model cache."""

    @abstractmethod
    def normalize_error(self, exc: BaseException) -> CanonicalError:
        """Map a provider-native exception to the canonical seven-category enum."""


# ---------------------------------------------------------------------------
# AdapterRegistry — process-scope mapping of env-var values to classes
# ---------------------------------------------------------------------------


class AdapterRegistry:
    """Process-scope mapping of adapter names to classes (read-only after startup)."""

    _REGISTRY: dict[str, type[ProviderAdapter]] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type[ProviderAdapter]) -> None:
        """Register an adapter class under `name`. Raises on duplicate."""
        if name in cls._REGISTRY:
            raise ValueError(f"Adapter {name!r} already registered")
        cls._REGISTRY[name] = adapter_cls

    @classmethod
    def get(cls, name: str) -> type[ProviderAdapter] | None:
        """Return the registered class for `name`, or None if unregistered."""
        return cls._REGISTRY.get(name)

    @classmethod
    def names(cls) -> list[str]:
        """Return the sorted list of registered adapter names."""
        return sorted(cls._REGISTRY.keys())

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Test-only registry clear. Do not call from production code."""
        cls._REGISTRY.clear()


# ---------------------------------------------------------------------------
# Process-scope active-adapter slot + lifecycle
# ---------------------------------------------------------------------------


_ACTIVE_ADAPTER: ProviderAdapter | None = None


def initialize_adapter() -> None:
    """Read SACP_PROVIDER_ADAPTER, instantiate the chosen adapter, store it.

    Called once during FastAPI startup AFTER `validate_all()` runs and
    BEFORE the router accepts connections. Topology 7 short-circuits
    per research.md §10. Double-init raises per research.md §5.
    """
    global _ACTIVE_ADAPTER
    topology = os.environ.get("SACP_TOPOLOGY", "1")
    if topology == "7":
        log.info("[startup] Topology 7 (MCP-to-MCP) active; provider adapter not initialized.")
        return
    if _ACTIVE_ADAPTER is not None:
        raise RuntimeError(
            "Adapter already initialized; mid-process swap is OUT OF SCOPE per spec 020 FR-015."
        )
    name = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm").strip().lower()
    cls = AdapterRegistry.get(name)
    if cls is None:
        raise SystemExit(
            f"SACP_PROVIDER_ADAPTER={name!r} is not a registered adapter. "
            f"Registered adapters: {AdapterRegistry.names()}"
        )
    _ACTIVE_ADAPTER = cls()
    log.info(
        "[startup] Provider adapter: %s (%s)",
        name,
        _adapter_banner_detail(name),
    )


def _adapter_banner_detail(name: str) -> str:
    """Render the parenthetical detail for the startup banner per quickstart §1."""
    if name == "litellm":
        return "default; SACP_PROVIDER_ADAPTER unset or =litellm"
    if name == "mock":
        path = os.environ.get("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", "<unset>")
        return f"fixtures: {path}"
    return name


def get_adapter() -> ProviderAdapter:
    """Return the process-scope active adapter."""
    if _ACTIVE_ADAPTER is None:
        topology = os.environ.get("SACP_TOPOLOGY", "1")
        if topology == "7":
            raise RuntimeError("topology 7 has no bridge layer; this code path should not execute")
        raise RuntimeError("Adapter not initialized. Call initialize_adapter() during startup.")
    return _ACTIVE_ADAPTER


def _reset_adapter_for_tests() -> None:
    """Test-only adapter slot clear. Do not call from production code."""
    global _ACTIVE_ADAPTER
    _ACTIVE_ADAPTER = None
