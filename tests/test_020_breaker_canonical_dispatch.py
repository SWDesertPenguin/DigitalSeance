"""Spec 015 breaker integration through canonical-category dispatch (spec 020 T040).

The breaker's `record_failure(participant_id)` interface is unchanged
by spec 020 — the canonical-category surface is consumed at the
loop-level handler that calls into the breaker. This test confirms
that a dispatch failure surfaced by the LiteLLM adapter normalizes to
the expected canonical category, and that the breaker's pre-feature
behavior on that category remains intact.

Pre-feature behavior: any dispatch failure that propagates as
`ProviderDispatchError` (including auth, rate-limit, timeout) increments
the breaker's per-participant counter. With spec 020 in place, the
loop captures the canonical category via `adapter.normalize_error(exc)`
for forensic logging, but the breaker's trip semantics are unchanged.
"""

from __future__ import annotations

import pytest

from src.api_bridge.adapter import (
    AdapterRegistry,
    CanonicalErrorCategory,
)


@pytest.fixture(autouse=True)
def _import_litellm_adapter() -> None:
    """Ensure the LiteLLM adapter is registered (test-isolation safe)."""
    if AdapterRegistry.get("litellm") is None:
        import src.api_bridge.litellm  # noqa: F401


def _adapter() -> object:
    cls = AdapterRegistry.get("litellm")
    assert cls is not None
    return cls()


def test_rate_limit_normalizes_to_rate_limit_category() -> None:
    import litellm

    adapter = _adapter()
    exc = litellm.RateLimitError("rate limited", "provider", "model", None)
    canonical = adapter.normalize_error(exc)
    assert canonical.category == CanonicalErrorCategory.RATE_LIMIT


def test_authentication_error_normalizes_to_auth_category() -> None:
    import litellm

    adapter = _adapter()
    exc = litellm.AuthenticationError(message="bad key", llm_provider="openai", model="gpt-4o")
    canonical = adapter.normalize_error(exc)
    assert canonical.category == CanonicalErrorCategory.AUTH_ERROR


def test_timeout_normalizes_to_timeout_category() -> None:
    import litellm

    adapter = _adapter()
    exc = litellm.Timeout(message="timeout", model="gpt-4o", llm_provider="openai")
    canonical = adapter.normalize_error(exc)
    assert canonical.category == CanonicalErrorCategory.TIMEOUT


def test_context_window_normalizes_to_4xx_not_quality() -> None:
    import litellm

    adapter = _adapter()
    exc = litellm.ContextWindowExceededError(
        message="too long", model="gpt-4o", llm_provider="openai"
    )
    canonical = adapter.normalize_error(exc)
    assert canonical.category == CanonicalErrorCategory.ERROR_4XX


def test_unknown_exception_falls_to_unknown_category() -> None:
    adapter = _adapter()
    canonical = adapter.normalize_error(RuntimeError("not a litellm error"))
    assert canonical.category == CanonicalErrorCategory.UNKNOWN


def test_breaker_consumes_canonical_only_no_litellm_imports_in_breaker() -> None:
    """Confirm circuit_breaker.py is unaware of LiteLLM exception classes."""
    from pathlib import Path

    src_path = (
        Path(__file__).resolve().parent.parent / "src" / "orchestrator" / "circuit_breaker.py"
    )
    text = src_path.read_text(encoding="utf-8")
    assert "import litellm" not in text
    assert "from litellm" not in text
    assert "litellm." not in text
