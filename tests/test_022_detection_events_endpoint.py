# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 endpoint-helper unit tests (T024 of tasks.md).

Covers the non-DB unit surface of ``src/mcp_server/tools/detection_events.py``:

- Env-var resolvers (``_resolved_max_events``, ``_resolved_since``,
  ``is_detection_history_enabled``).
- Master-switch parsing edge cases (truthy variants, malformed values).
- Row → wire-shape decoration via ``_decorate_event``.
- Authorization helper (facilitator-only + session-bound).

The full endpoint integration (DB lookup + cookie-auth + WS broadcast)
lives in tests/integration/ behind the @pytest.mark.integration marker
and is exercised in the slow CI tier (T024b in a follow-up commit).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.mcp_server.tools import detection_events as endpoint


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SACP_DETECTION_HISTORY_ENABLED",
        "SACP_DETECTION_HISTORY_MAX_EVENTS",
        "SACP_DETECTION_HISTORY_RETENTION_DAYS",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# is_detection_history_enabled
# ---------------------------------------------------------------------------


def test_is_enabled_unset_returns_false() -> None:
    assert endpoint.is_detection_history_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "True", "1"])
def test_is_enabled_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_ENABLED", value)
    assert endpoint.is_detection_history_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "", "yes", "on"])
def test_is_enabled_non_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_ENABLED", value)
    assert endpoint.is_detection_history_enabled() is False


# ---------------------------------------------------------------------------
# _resolved_max_events
# ---------------------------------------------------------------------------


def test_resolved_max_events_unset_returns_none() -> None:
    assert endpoint._resolved_max_events() is None


def test_resolved_max_events_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", "")
    assert endpoint._resolved_max_events() is None


@pytest.mark.parametrize("value,expected", [("1", 1), ("50", 50), ("100000", 100000)])
def test_resolved_max_events_valid(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: int
) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", value)
    assert endpoint._resolved_max_events() == expected


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_resolved_max_events_invalid_returns_none(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_MAX_EVENTS", value)
    assert endpoint._resolved_max_events() is None


# ---------------------------------------------------------------------------
# _resolved_since
# ---------------------------------------------------------------------------


def test_resolved_since_unset_returns_none() -> None:
    assert endpoint._resolved_since() is None


def test_resolved_since_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", "")
    assert endpoint._resolved_since() is None


def test_resolved_since_valid_returns_recent_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", "30")
    result = endpoint._resolved_since()
    assert result is not None
    assert result.tzinfo is not None
    expected = datetime.now(UTC) - timedelta(days=30)
    assert abs((result - expected).total_seconds()) < 5


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_resolved_since_invalid_returns_none(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_DETECTION_HISTORY_RETENTION_DAYS", value)
    assert endpoint._resolved_since() is None


# ---------------------------------------------------------------------------
# _decorate_event
# ---------------------------------------------------------------------------


def test_decorate_event_full_row() -> None:
    row = {
        "id": 1037,
        "event_class": "ai_question_opened",
        "participant_id": "p1",
        "trigger_snippet": "what should we do?",
        "detector_score": 0.87,
        "turn_number": 14,
        "timestamp": datetime(2026, 5, 11, 14, 32, 1, 234000, tzinfo=UTC),
        "disposition": "pending",
        "last_disposition_change_at": None,
    }
    out = endpoint._decorate_event(row)
    assert out["event_id"] == 1037
    assert out["event_class"] == "ai_question_opened"
    assert out["event_class_label"] == "AI question opened"
    assert out["participant_id"] == "p1"
    assert out["trigger_snippet"] == "what should we do?"
    assert out["detector_score"] == 0.87
    assert out["turn_number"] == 14
    assert isinstance(out["timestamp"], str) and out["timestamp"].endswith("Z")
    assert out["disposition"] == "pending"
    assert out["last_disposition_change_at"] is None


def test_decorate_event_with_disposition_change() -> None:
    changed = datetime(2026, 5, 11, 15, 0, 0, tzinfo=UTC)
    row = {
        "id": 99,
        "event_class": "density_anomaly",
        "participant_id": "p2",
        "trigger_snippet": None,
        "detector_score": None,
        "turn_number": None,
        "timestamp": datetime(2026, 5, 11, 14, 0, 0, tzinfo=UTC),
        "disposition": "banner_dismissed",
        "last_disposition_change_at": changed,
    }
    out = endpoint._decorate_event(row)
    assert out["event_class_label"] == "Density anomaly"
    assert out["last_disposition_change_at"] is not None
    assert out["last_disposition_change_at"].endswith("Z")


def test_decorate_event_unregistered_class_renders_fallback() -> None:
    row = {
        "id": 1,
        "event_class": "future_class_not_in_registry",
        "participant_id": "p1",
        "trigger_snippet": None,
        "detector_score": None,
        "turn_number": None,
        "timestamp": datetime(2026, 5, 11, 14, 0, 0, tzinfo=UTC),
        "disposition": "pending",
        "last_disposition_change_at": None,
    }
    out = endpoint._decorate_event(row)
    assert out["event_class_label"].startswith("[unregistered:")


# ---------------------------------------------------------------------------
# _authorize
# ---------------------------------------------------------------------------


def test_authorize_facilitator_same_session_passes() -> None:
    participant = SimpleNamespace(role="facilitator", session_id="s1")
    endpoint._authorize(participant, "s1")


def test_authorize_non_facilitator_raises_403() -> None:
    participant = SimpleNamespace(role="ai", session_id="s1")
    with pytest.raises(HTTPException) as excinfo:
        endpoint._authorize(participant, "s1")
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail.get("error") == "facilitator_only"


def test_authorize_cross_session_raises_403() -> None:
    participant = SimpleNamespace(role="facilitator", session_id="s1")
    with pytest.raises(HTTPException) as excinfo:
        endpoint._authorize(participant, "s2")
    assert excinfo.value.status_code == 403


# ---------------------------------------------------------------------------
# Module-shape sanity
# ---------------------------------------------------------------------------


def test_router_prefix_is_admin_namespace() -> None:
    assert endpoint.router.prefix == "/tools/admin"
