"""API bridge — pluggable provider adapter abstraction with LiteLLM and mock implementations.

Spec 020 dissolves the prior `src.api_bridge.provider` module into a
`ProviderAdapter` interface (`src.api_bridge.adapter`) plus two
implementations: `src.api_bridge.litellm` (production-path) and
`src.api_bridge.mock` (deterministic test adapter).

Re-exports the canonical types and the lifecycle helpers so consumers
can `from src.api_bridge import get_adapter, ProviderRequest` instead
of reaching into the adapter module.
"""

from __future__ import annotations

from src.api_bridge.adapter import (
    AdapterRegistry,
    CanonicalError,
    CanonicalErrorCategory,
    Capabilities,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    StreamEvent,
    StreamEventType,
    ValidationResult,
    get_adapter,
    initialize_adapter,
)

__all__ = [
    "AdapterRegistry",
    "Capabilities",
    "CanonicalError",
    "CanonicalErrorCategory",
    "ProviderAdapter",
    "ProviderRequest",
    "ProviderResponse",
    "StreamEvent",
    "StreamEventType",
    "ValidationResult",
    "get_adapter",
    "initialize_adapter",
]
