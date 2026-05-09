"""US2 acceptance scenarios 1 + 2: mock dispatch + injectable error modes."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api_bridge.adapter import (
    AdapterRegistry,
    CanonicalErrorCategory,
    ProviderRequest,
)
from src.api_bridge.mock.errors import MockInjectedError

pytestmark = pytest.mark.no_adapter_autoinit

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASIC = _REPO_ROOT / "tests" / "fixtures" / "mock_adapter" / "basic_responses.json"
_ERRORS = _REPO_ROOT / "tests" / "fixtures" / "mock_adapter" / "error_modes.json"


@pytest.fixture(autouse=True)
def _import_mock() -> None:
    if AdapterRegistry.get("mock") is None:
        import src.api_bridge.mock  # noqa: F401


def _request(content: str) -> ProviderRequest:
    return ProviderRequest(
        model="mock-model",
        messages=[{"role": "user", "content": content}],
        api_key_encrypted=None,
        encryption_key="",
    )


def _build_mock(monkeypatch: pytest.MonkeyPatch, fixtures_path: Path) -> object:
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", str(fixtures_path))
    cls = AdapterRegistry.get("mock")
    assert cls is not None
    return cls()


@pytest.mark.asyncio
async def test_mock_returns_fixture_keyed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2 scenario 1: configured fixture returns matching response + token counts."""
    adapter = _build_mock(monkeypatch, _BASIC)
    response = await adapter.dispatch_with_retry(_request("say hello to me"))
    assert response.content == "hello world"
    assert response.input_tokens == 42
    assert response.output_tokens == 10


@pytest.mark.asyncio
async def test_mock_5xx_normalize_to_5xx_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US2 scenario 2: 5xx fixture -> normalize_error -> ERROR_5XX category."""
    adapter = _build_mock(monkeypatch, _ERRORS)
    with pytest.raises(MockInjectedError) as excinfo:
        await adapter.dispatch_with_retry(_request("please trigger 5xx"))
    canonical = adapter.normalize_error(excinfo.value)
    assert canonical.category == CanonicalErrorCategory.ERROR_5XX


@pytest.mark.asyncio
async def test_mock_rate_limit_carries_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _build_mock(monkeypatch, _ERRORS)
    with pytest.raises(MockInjectedError) as excinfo:
        await adapter.dispatch_with_retry(_request("please trigger rate limit"))
    canonical = adapter.normalize_error(excinfo.value)
    assert canonical.category == CanonicalErrorCategory.RATE_LIMIT
    assert canonical.retry_after_seconds == 30


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trigger,expected",
    [
        ("trigger 4xx", CanonicalErrorCategory.ERROR_4XX),
        ("trigger auth", CanonicalErrorCategory.AUTH_ERROR),
        ("trigger timeout", CanonicalErrorCategory.TIMEOUT),
        ("trigger quality", CanonicalErrorCategory.QUALITY_FAILURE),
        ("trigger unknown", CanonicalErrorCategory.UNKNOWN),
    ],
)
async def test_mock_each_canonical_category_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    trigger: str,
    expected: CanonicalErrorCategory,
) -> None:
    """SC-003: spec 015 breaker tests can drive every canonical category."""
    adapter = _build_mock(monkeypatch, _ERRORS)
    with pytest.raises(MockInjectedError) as excinfo:
        await adapter.dispatch_with_retry(_request(f"please {trigger}"))
    canonical = adapter.normalize_error(excinfo.value)
    assert canonical.category == expected
