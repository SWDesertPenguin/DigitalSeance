"""Playwright fixtures shared by all Phase 2 e2e tests.

The tests assume a running SACP stack. Rather than starting one here,
we read connection details from the environment so CI pipelines can
spin up their own docker compose instance and point the suite at it.

Env vars:
    SACP_RUN_E2E           "1" to opt into this module; missing = skip all.
    SACP_WEB_UI_BASE_URL   default http://localhost:8751
    SACP_MCP_BASE_URL      default http://localhost:8750
    SACP_E2E_FACILITATOR_TOKEN  required — an already-provisioned
                            facilitator bearer token for the test session.

To set up locally:
    uv pip install -e '.[e2e]'
    playwright install chromium
    docker compose up -d
    export SACP_E2E_FACILITATOR_TOKEN=$(curl -s -XPOST \
        http://localhost:8750/tools/session/create \
        -H 'Content-Type: application/json' \
        -d '{"name":"e2e","display_name":"Tester"}' | jq -r .auth_token)
    SACP_RUN_E2E=1 pytest tests/e2e/ -v
"""

from __future__ import annotations

import os
from typing import Any

import pytest


def pytest_collection_modifyitems(
    config: Any,
    items: list[Any],
) -> None:
    """Skip the whole module unless SACP_RUN_E2E=1 is set."""
    if os.environ.get("SACP_RUN_E2E") == "1":
        return
    skip_reason = pytest.mark.skip(
        reason="SACP_RUN_E2E not set — skipping Playwright e2e tests",
    )
    for item in items:
        if "tests/e2e" in str(getattr(item, "fspath", "")).replace("\\", "/"):
            item.add_marker(skip_reason)


@pytest.fixture(scope="session")
def web_ui_base_url() -> str:
    """Absolute base URL for the SACP Web UI."""
    return os.environ.get("SACP_WEB_UI_BASE_URL", "http://localhost:8751")


@pytest.fixture(scope="session")
def mcp_base_url() -> str:
    """Absolute base URL for the SACP MCP server."""
    return os.environ.get("SACP_MCP_BASE_URL", "http://localhost:8750")


@pytest.fixture(scope="session")
def facilitator_token() -> str:
    """Bearer token for the test session's facilitator."""
    token = os.environ.get("SACP_E2E_FACILITATOR_TOKEN")
    if not token:
        pytest.skip("SACP_E2E_FACILITATOR_TOKEN not set")
    return token


@pytest.fixture
def signed_in_page(
    page: Any,
    web_ui_base_url: str,
    facilitator_token: str,
) -> Any:
    """Return a Playwright Page that has already completed /login.

    Drives the AuthGate form with the real token and waits for the
    SessionView header to render. Test bodies inherit a live cookie +
    React-ref token without duplicating the login dance.
    """
    page.goto(web_ui_base_url)
    page.locator("input[type=password]").fill(facilitator_token)
    page.get_by_role("button", name="Sign in").click()
    # SessionView renders a connection indicator in the top-right.
    page.wait_for_selector(".ws-indicator", timeout=10_000)
    return page
