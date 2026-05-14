# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for the spec 029 admin endpoint resolver helpers.

The endpoint route in ``src/participant_api/tools/admin.py`` reads three env
vars at call time. These tests validate the parsers without spinning up
a FastAPI app or hitting the DB:

- ``is_audit_viewer_enabled()`` — master switch parser (FR-018)
- ``_resolve_limit()`` — page-size cap with 400 on out-of-range (FR-005)
- ``_resolved_retention_days()`` — empty -> None, set -> int (FR-016)

DB-bound endpoint contract tests (T016 of tasks.md) cover the auth,
ordering, and pagination behavior end-to-end via TestClient.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.participant_api.tools import admin


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the three audit-viewer vars unset."""
    for var in (
        "SACP_AUDIT_VIEWER_ENABLED",
        "SACP_AUDIT_VIEWER_PAGE_SIZE",
        "SACP_AUDIT_VIEWER_RETENTION_DAYS",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# is_audit_viewer_enabled
# ---------------------------------------------------------------------------


def test_master_switch_default_disabled() -> None:
    assert admin.is_audit_viewer_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "True", "1"])
def test_master_switch_enabled_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_ENABLED", value)
    assert admin.is_audit_viewer_enabled() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "", "garbage"])
def test_master_switch_disabled_falsy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_ENABLED", value)
    assert admin.is_audit_viewer_enabled() is False


# ---------------------------------------------------------------------------
# _resolve_limit
# ---------------------------------------------------------------------------


def test_resolve_limit_default_when_unset() -> None:
    assert admin._resolve_limit(None) == admin.DEFAULT_PAGE_SIZE


def test_resolve_limit_uses_env_max_as_default_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", "25")
    # default 50 is above the env max of 25; default falls to 25.
    assert admin._resolve_limit(None) == 25


def test_resolve_limit_accepts_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", "100")
    assert admin._resolve_limit(75) == 75


@pytest.mark.parametrize("value", [0, -1, 501, 9999])
def test_resolve_limit_rejects_out_of_range(value: int) -> None:
    with pytest.raises(HTTPException) as excinfo:
        admin._resolve_limit(value)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["error"] == "invalid_params"


def test_resolve_limit_rejects_above_env_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_PAGE_SIZE", "20")
    with pytest.raises(HTTPException) as excinfo:
        admin._resolve_limit(100)
    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# _resolved_retention_days
# ---------------------------------------------------------------------------


def test_retention_unset_returns_none() -> None:
    assert admin._resolved_retention_days() is None


def test_retention_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", "")
    assert admin._resolved_retention_days() is None


def test_retention_set_returns_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", "30")
    assert admin._resolved_retention_days() == 30


def test_retention_zero_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive fallback — validator already guards but be safe."""
    monkeypatch.setenv("SACP_AUDIT_VIEWER_RETENTION_DAYS", "0")
    assert admin._resolved_retention_days() is None
