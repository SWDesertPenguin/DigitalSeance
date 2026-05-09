"""US1 acceptance scenario 1 smoke test (SC-001 byte-identical regression).

The full byte-identical regression contract is enforced by running the
pre-feature acceptance suite with `SACP_PROVIDER_ADAPTER=litellm`
(default) per the CI matrix entry T022. This file documents the
contract via a smoke test — it confirms the LiteLLM adapter is the
default and that `get_adapter()` returns a `LiteLLMAdapter` instance.
"""

from __future__ import annotations

import pytest

from src.api_bridge.adapter import (
    AdapterRegistry,
    _reset_adapter_for_tests,
    get_adapter,
    initialize_adapter,
)

pytestmark = pytest.mark.no_adapter_autoinit


@pytest.fixture
def _registered() -> None:
    if AdapterRegistry.get("litellm") is None:
        import src.api_bridge.litellm  # noqa: F401


def test_default_adapter_is_litellm(monkeypatch: pytest.MonkeyPatch, _registered: None) -> None:
    """SC-001: with no env override, the active adapter is LiteLLMAdapter."""
    from src.api_bridge.litellm.adapter import LiteLLMAdapter

    monkeypatch.delenv("SACP_PROVIDER_ADAPTER", raising=False)
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    _reset_adapter_for_tests()
    try:
        initialize_adapter()
        active = get_adapter()
        assert type(active).__name__ == "LiteLLMAdapter"
        assert isinstance(active, LiteLLMAdapter)
    finally:
        _reset_adapter_for_tests()
