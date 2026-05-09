"""Unit tests for the spec 020 adapter ABC, registry, and factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

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
    _reset_adapter_for_tests,
    get_adapter,
    initialize_adapter,
)

pytestmark = pytest.mark.no_adapter_autoinit


class _FakeAdapter(ProviderAdapter):
    """Minimal subclass for registry / factory tests."""

    name = "fake_test"

    async def dispatch(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError

    async def dispatch_with_retry(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError

    async def stream(self, request: ProviderRequest) -> AsyncIterator[StreamEvent]:
        if False:
            yield StreamEvent(event_type=StreamEventType.FINALIZATION)
        return

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        return 0

    async def validate_credentials(self, api_key: str, model: str) -> ValidationResult:
        return ValidationResult(ok=True)

    def capabilities(self, model: str) -> Capabilities:
        return Capabilities(
            supports_streaming=True,
            supports_tool_calling=True,
            supports_prompt_caching=False,
            max_context_tokens=200000,
            tokenizer_name="fake",
            recommended_temperature_range=(0.0, 1.0),
            provider_family="fake",
        )

    def normalize_error(self, exc: BaseException) -> CanonicalError:
        return CanonicalError(category=CanonicalErrorCategory.UNKNOWN)


@pytest.fixture
def clean_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Snapshot the registry; restore after the test."""
    original = dict(AdapterRegistry._REGISTRY)
    monkeypatch.delenv("SACP_PROVIDER_ADAPTER", raising=False)
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    _reset_adapter_for_tests()
    yield
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry._REGISTRY.update(original)
    _reset_adapter_for_tests()


def test_register_and_get(clean_registry: None) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("alpha", _FakeAdapter)
    assert AdapterRegistry.get("alpha") is _FakeAdapter
    assert AdapterRegistry.names() == ["alpha"]


def test_register_duplicate_raises(clean_registry: None) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("alpha", _FakeAdapter)
    with pytest.raises(ValueError, match="already registered"):
        AdapterRegistry.register("alpha", _FakeAdapter)


def test_get_unregistered_returns_none(clean_registry: None) -> None:
    AdapterRegistry._REGISTRY.clear()
    assert AdapterRegistry.get("missing") is None


def test_names_returns_sorted(clean_registry: None) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("zeta", _FakeAdapter)

    class _AnotherAdapter(_FakeAdapter):
        pass

    AdapterRegistry.register("alpha", _AnotherAdapter)
    assert AdapterRegistry.names() == ["alpha", "zeta"]


def test_get_adapter_before_init_raises(clean_registry: None) -> None:
    with pytest.raises(RuntimeError, match="Adapter not initialized"):
        get_adapter()


def test_initialize_adapter_invalid_name_exits(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("litellm", _FakeAdapter)
    AdapterRegistry.register("mock", _FakeAdapter)
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER", "rabbit")
    with pytest.raises(SystemExit) as excinfo:
        initialize_adapter()
    msg = str(excinfo.value)
    assert "rabbit" in msg
    assert "litellm" in msg
    assert "mock" in msg


def test_initialize_adapter_default_litellm(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("litellm", _FakeAdapter)
    initialize_adapter()
    assert isinstance(get_adapter(), _FakeAdapter)


def test_initialize_adapter_double_init_raises(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("litellm", _FakeAdapter)
    initialize_adapter()
    with pytest.raises(RuntimeError, match="already initialized"):
        initialize_adapter()


def test_initialize_adapter_topology_7_skips(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("litellm", _FakeAdapter)
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    initialize_adapter()
    with pytest.raises(RuntimeError, match="topology 7 has no bridge layer"):
        get_adapter()


def test_initialize_adapter_explicit_mock(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    AdapterRegistry._REGISTRY.clear()

    class _MockSub(_FakeAdapter):
        name = "mock"

    AdapterRegistry.register("litellm", _FakeAdapter)
    AdapterRegistry.register("mock", _MockSub)
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER", "mock")
    initialize_adapter()
    assert isinstance(get_adapter(), _MockSub)


def test_us3_future_adapter_loads_via_registry(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    """US3 acceptance scenario 3: future adapter via registry registration."""
    AdapterRegistry._REGISTRY.clear()

    class FutureAdapter(_FakeAdapter):
        pass

    AdapterRegistry.register("future_test", FutureAdapter)
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER", "future_test")
    initialize_adapter()
    assert isinstance(get_adapter(), FutureAdapter)


def test_us3_invalid_lists_registered_names(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    """US3 acceptance scenario 2 / SC-005."""
    AdapterRegistry._REGISTRY.clear()
    AdapterRegistry.register("litellm", _FakeAdapter)
    AdapterRegistry.register("mock", _FakeAdapter)
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER", "definitely-not-registered")
    with pytest.raises(SystemExit) as excinfo:
        initialize_adapter()
    msg = str(excinfo.value)
    assert "Registered adapters" in msg
    assert "['litellm', 'mock']" in msg or ("'litellm'" in msg and "'mock'" in msg)


def test_us3_dispatch_path_files_dont_import_adapter_packages() -> None:
    """US3 acceptance scenario 1: dispatch-path code doesn't name a specific
    adapter package — only the abstraction module."""
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "src"
    forbidden = re.compile(
        r"^\s*(?:import|from)\s+src\.api_bridge\.(?:litellm|mock)\b",
        re.MULTILINE,
    )
    dispatch_files = [
        src / "orchestrator" / "loop.py",
        src / "orchestrator" / "summarizer.py",
        src / "orchestrator" / "circuit_breaker.py",
    ]
    for path in dispatch_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        match = forbidden.search(text)
        assert match is None, f"{path} imports a specific adapter package: {match.group(0)!r}"


def test_us3_both_adapters_coexist_only_selected_instantiated(
    monkeypatch: pytest.MonkeyPatch,
    clean_registry: None,
) -> None:
    """US3 acceptance scenario 4: both classes registered; one instantiated."""
    AdapterRegistry._REGISTRY.clear()

    class LiteLLMSub(_FakeAdapter):
        pass

    class MockSub(_FakeAdapter):
        pass

    AdapterRegistry.register("litellm", LiteLLMSub)
    AdapterRegistry.register("mock", MockSub)
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER", "mock")
    initialize_adapter()
    active = get_adapter()
    assert isinstance(active, MockSub)
    assert not isinstance(active, LiteLLMSub)
    # The unselected class still exists in the registry.
    assert AdapterRegistry.get("litellm") is LiteLLMSub
