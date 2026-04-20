"""MCP tool endpoint tests — basic route validation."""

from __future__ import annotations

from src.mcp_server.app import create_app
from src.mcp_server.tools.session import (
    _format_json_message,
    _format_md_message,
)


def test_markdown_format() -> None:
    """Markdown formatter produces expected output."""

    class _FakeMsg:
        speaker_type = "human"
        content = "Hello world"
        turn_number = 0
        speaker_id = "alice"

    result = _format_md_message(_FakeMsg())
    assert "**[human]**" in result
    assert "Hello world" in result


def test_json_format() -> None:
    """JSON formatter produces expected structure."""

    class _FakeMsg:
        speaker_type = "ai"
        content = "Response text"
        turn_number = 1
        speaker_id = "bob"

    result = _format_json_message(_FakeMsg())
    assert result["turn"] == 1
    assert result["type"] == "ai"
    assert result["content"] == "Response text"


def test_app_routes_registered() -> None:
    """All expected tool routes exist."""
    app = create_app()
    paths = {r.path for r in app.routes}
    expected = [
        "/tools/participant/inject_message",
        "/tools/participant/status",
        "/tools/participant/history",
        "/tools/facilitator/create_invite",
        "/tools/facilitator/approve_participant",
        "/tools/session/create",
        "/tools/session/pause",
        "/tools/session/start_loop",
    ]
    for path in expected:
        assert path in paths, f"Missing route: {path}"


def test_t250_t251_routes_registered() -> None:
    """Backend gap endpoints exposed for Phase 2b Web UI (T250, T251)."""
    app = create_app()
    paths = {r.path for r in app.routes}
    new_routes = [
        # T250 — self-serve routing preference
        "/tools/participant/set_routing_preference",
        # T251 — session config mutations
        "/tools/facilitator/set_cadence_preset",
        "/tools/facilitator/set_acceptance_mode",
        "/tools/facilitator/set_min_model_tier",
        "/tools/facilitator/set_complexity_classifier_mode",
    ]
    for path in new_routes:
        assert path in paths, f"Missing route: {path}"


def test_t252_audit_entry_event_shape() -> None:
    """audit_entry event uses the v1 envelope."""
    from src.web_ui.events import audit_entry_event

    evt = audit_entry_event({"id": 1, "action": "approve_participant"})
    assert evt["v"] == 1
    assert evt["type"] == "audit_entry"
    assert evt["entry"]["action"] == "approve_participant"
