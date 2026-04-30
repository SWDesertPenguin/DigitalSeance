"""Per-test FastAPI app fixture isolation tests (spec 012 FR-009 / US7).

Verifies the `mcp_app` and `web_app` fixtures in conftest.py provide
fresh app instances per test so middleware state, app.state attributes,
and other per-app stores cannot leak across tests.
"""

from __future__ import annotations


def test_mcp_app_is_fresh_per_test(mcp_app: object) -> None:
    """Each test receives a distinct FastAPI app object."""
    from fastapi import FastAPI

    assert isinstance(mcp_app, FastAPI)
    assert not hasattr(
        mcp_app.state, "_us7_marker"
    ), "app.state._us7_marker leaked from a prior test — fixture is not isolating"


def test_mcp_app_state_does_not_leak_a(mcp_app: object) -> None:
    """First half of the cross-test leak check — sets a marker on the app."""
    mcp_app.state._us7_marker = "test_a"  # type: ignore[attr-defined]
    assert mcp_app.state._us7_marker == "test_a"  # type: ignore[attr-defined]


def test_mcp_app_state_does_not_leak_b(mcp_app: object) -> None:
    """Second half — confirms no marker survives from the prior test."""
    assert not hasattr(
        mcp_app.state, "_us7_marker"
    ), "test_a's app.state._us7_marker survived into test_b — fixture is not isolating"


def test_two_apps_in_same_test_are_distinct_objects(
    mcp_app: object,
    web_app: object,
) -> None:
    """mcp_app and web_app are different FastAPI instances."""
    assert mcp_app is not web_app
