"""US2: MockFixtureMissingError on unconfigured input per FR-007 + SC-004."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api_bridge.adapter import AdapterRegistry, ProviderRequest
from src.api_bridge.mock.errors import MockFixtureMissingError

pytestmark = pytest.mark.no_adapter_autoinit

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASIC = _REPO_ROOT / "tests" / "fixtures" / "mock_adapter" / "basic_responses.json"


@pytest.fixture(autouse=True)
def _import_mock() -> None:
    if AdapterRegistry.get("mock") is None:
        import src.api_bridge.mock  # noqa: F401


@pytest.mark.asyncio
async def test_mock_fixture_missing_names_canonical_hash_and_substring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unconfigured input -> exception names canonical hash + substring."""
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", str(_BASIC))
    cls = AdapterRegistry.get("mock")
    assert cls is not None
    adapter = cls()
    request = ProviderRequest(
        model="mock-model",
        messages=[{"role": "user", "content": "no fixture for this content"}],
        api_key_encrypted=None,
        encryption_key="",
    )
    with pytest.raises(MockFixtureMissingError) as excinfo:
        await adapter.dispatch_with_retry(request)
    msg = str(excinfo.value)
    assert "canonical_hash=" in msg
    assert "last_message_substring=" in msg
    assert excinfo.value.canonical_hash  # non-empty hex
    assert "no fixture for this content" in excinfo.value.last_message_substring
