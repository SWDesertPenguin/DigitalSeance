# SPDX-License-Identifier: AGPL-3.0-or-later

"""US2 acceptance scenario 3: mock adapter makes no outbound network call."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from src.api_bridge.adapter import AdapterRegistry, ProviderRequest

pytestmark = pytest.mark.no_adapter_autoinit

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASIC = _REPO_ROOT / "tests" / "fixtures" / "mock_adapter" / "basic_responses.json"


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


@pytest.mark.asyncio
async def test_mock_dispatch_makes_no_outbound_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the mock adapter ever opens a socket, this test fails."""
    monkeypatch.setenv("SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH", str(_BASIC))
    cls = AdapterRegistry.get("mock")
    assert cls is not None
    adapter = cls()

    def _refuse_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "MockAdapter attempted an outbound socket connection — "
            "network isolation invariant violated"
        )

    monkeypatch.setattr(socket, "create_connection", _refuse_connect)
    response = await adapter.dispatch_with_retry(_request("hello there"))
    assert response.content == "hello world"
