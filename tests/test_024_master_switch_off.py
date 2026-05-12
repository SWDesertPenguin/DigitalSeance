# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 024 FR-019 master-switch-off canary.

When ``SACP_SCRATCH_ENABLED`` is unset or ``'0'`` (default), no
scratch route is mounted on the FastAPI app surface. The check
runs against ``app.routes`` directly without entering the lifespan
(which requires DB/env wiring).
"""

from __future__ import annotations

import pytest

from src.mcp_server.app import create_app
from src.scratch.router import is_scratch_enabled

_SCRATCH_PREFIX = "/tools/facilitator/scratch"


@pytest.fixture(autouse=True)
def _switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the master switch unset."""
    monkeypatch.delenv("SACP_SCRATCH_ENABLED", raising=False)


def test_is_scratch_enabled_default_false() -> None:
    assert is_scratch_enabled() is False


@pytest.mark.parametrize("value", ["0", "", "false", "garbage"])
def test_is_scratch_enabled_falsey(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("SACP_SCRATCH_ENABLED", value)
    assert is_scratch_enabled() is False


def test_is_scratch_enabled_only_on_with_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_SCRATCH_ENABLED", "1")
    assert is_scratch_enabled() is True


def test_no_scratch_routes_when_switch_off() -> None:
    """FR-019: absence-of-mount when switch is off."""
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}
    scratch_paths = {p for p in paths if p.startswith(_SCRATCH_PREFIX)}
    assert (
        scratch_paths == set()
    ), f"FR-019 leak: scratch routes mounted with switch off: {scratch_paths}"


def test_scratch_routes_mounted_when_switch_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-019 inverse: routes appear when the switch flips on."""
    monkeypatch.setenv("SACP_SCRATCH_ENABLED", "1")
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}
    scratch_paths = {p for p in paths if p.startswith(_SCRATCH_PREFIX)}
    assert (
        len(scratch_paths) >= 5
    ), f"FR-019 mount-on leak: expected scratch routes, got {scratch_paths}"
