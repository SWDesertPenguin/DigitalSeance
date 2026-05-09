"""US2 acceptance scenario 4: fixture-controllable capabilities()."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api_bridge.adapter import AdapterRegistry

pytestmark = pytest.mark.no_adapter_autoinit

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASIC = _REPO_ROOT / "tests" / "fixtures" / "mock_adapter" / "basic_responses.json"


@pytest.fixture(autouse=True)
def _import_mock() -> None:
    if AdapterRegistry.get("mock") is None:
        import src.api_bridge.mock  # noqa: F401


def _build(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", str(_BASIC))
    cls = AdapterRegistry.get("mock")
    assert cls is not None
    return cls()


def test_default_capability_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SACP_MOCK_CAPABILITY_SET", raising=False)
    adapter = _build(monkeypatch)
    cap = adapter.capabilities("any-model")
    assert cap.supports_tool_calling is True
    assert cap.max_context_tokens == 200_000
    assert cap.provider_family == "mock"


def test_no_tool_capability_set_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests can simulate 'no tool calling' via the capability-set knob."""
    monkeypatch.setenv("SACP_MOCK_CAPABILITY_SET", "no_tool_model")
    adapter = _build(monkeypatch)
    cap = adapter.capabilities("any-model")
    assert cap.supports_tool_calling is False
    assert cap.max_context_tokens == 8192
