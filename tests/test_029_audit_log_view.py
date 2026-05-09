# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 audit-log view dataclass + decorate_row coverage.

Covers the pure-logic helpers in ``src/orchestrator/audit_log_view.py``:

- ``decorate_row`` shape + display-name resolution + scrub passthrough
- ``resolve_display_name`` orchestrator / participant / deleted-participant cases
- ``resolve_target_display_name`` session-self / participant / deleted cases
- ``row_to_payload`` flattens the dataclass to the contract shape

These tests do NOT require Postgres — pure Python helpers driven by dict
fixtures. The DB-bound integration tests (T016-T019 in tasks.md) ride on
top of this contract and run in the integration tier.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.orchestrator.audit_log_view import (
    ORCHESTRATOR_DISPLAY_NAME,
    SCRUBBED_PLACEHOLDER,
    AuditLogPage,
    decorate_row,
    page_to_payload,
    resolve_display_name,
    resolve_target_display_name,
    row_to_payload,
)

SESSION_ID = "session-uuid-aaa"
ALICE_ID = "alice-uuid-1234abcd"
BOB_ID = "bob-uuid-5678efgh"
DELETED_ID = "deleted-uuid-zzzz0000"
NAME_BY_ID = {ALICE_ID: "Alice", BOB_ID: "Bob"}


# ---------------------------------------------------------------------------
# resolve_display_name
# ---------------------------------------------------------------------------


def test_resolve_display_name_orchestrator() -> None:
    assert resolve_display_name(None, NAME_BY_ID) == ORCHESTRATOR_DISPLAY_NAME


def test_resolve_display_name_known_participant() -> None:
    assert resolve_display_name(ALICE_ID, NAME_BY_ID) == "Alice"


def test_resolve_display_name_deleted_participant() -> None:
    out = resolve_display_name(DELETED_ID, NAME_BY_ID)
    assert out.startswith("<deleted-participant ")
    assert DELETED_ID[:8] in out


# ---------------------------------------------------------------------------
# resolve_target_display_name
# ---------------------------------------------------------------------------


def test_resolve_target_display_name_session_self() -> None:
    """target_id == session_id -> None (session-scoped action)."""
    assert resolve_target_display_name(SESSION_ID, SESSION_ID, NAME_BY_ID) is None


def test_resolve_target_display_name_null() -> None:
    assert resolve_target_display_name(None, SESSION_ID, NAME_BY_ID) is None


def test_resolve_target_display_name_participant() -> None:
    assert resolve_target_display_name(BOB_ID, SESSION_ID, NAME_BY_ID) == "Bob"


def test_resolve_target_display_name_deleted_participant() -> None:
    out = resolve_target_display_name(DELETED_ID, SESSION_ID, NAME_BY_ID)
    assert out is not None
    assert out.startswith("<deleted-participant ")


# ---------------------------------------------------------------------------
# decorate_row
# ---------------------------------------------------------------------------


def _record(**overrides: object) -> dict:
    base = {
        "id": 1,
        "timestamp": datetime(2026, 5, 8, 14, 30, 0, tzinfo=UTC),
        "facilitator_id": ALICE_ID,
        "action": "remove_participant",
        "target_id": BOB_ID,
        "previous_value": None,
        "new_value": None,
    }
    base.update(overrides)
    return base


def test_decorate_row_registered_action_and_label() -> None:
    row = decorate_row(_record(), session_id=SESSION_ID, name_by_id=NAME_BY_ID)
    assert row.action == "remove_participant"
    assert row.action_label == "Facilitator removed participant"
    assert row.actor_display_name == "Alice"
    assert row.target_display_name == "Bob"
    assert row.previous_value is None
    assert row.new_value is None


def test_decorate_row_unregistered_action_renders_fallback() -> None:
    row = decorate_row(
        _record(action="totally_made_up_action"),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
    )
    assert row.action_label == "[unregistered: totally_made_up_action]"


def test_decorate_row_scrub_replaces_values() -> None:
    """rotate_token has scrub_value=True — both values replaced by the placeholder."""
    row = decorate_row(
        _record(
            action="rotate_token",
            previous_value="old-secret-token-abc",
            new_value="new-secret-token-xyz",
        ),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
    )
    assert row.previous_value == SCRUBBED_PLACEHOLDER
    assert row.new_value == SCRUBBED_PLACEHOLDER


def test_decorate_row_scrub_leaves_nulls_alone() -> None:
    row = decorate_row(
        _record(action="rotate_token", previous_value=None, new_value=None),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
    )
    assert row.previous_value is None
    assert row.new_value is None


def test_decorate_row_session_scoped_action_target_is_null() -> None:
    """cap_set targets the session itself (target_id == session_id)."""
    row = decorate_row(
        _record(action="cap_set", target_id=SESSION_ID),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
    )
    assert row.target_id == SESSION_ID
    assert row.target_display_name is None


def test_decorate_row_orchestrator_actor_via_sentinel() -> None:
    row = decorate_row(
        _record(action="auto_pause_on_cap"),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
        orchestrator_actor_ids=frozenset({ALICE_ID}),
    )
    assert row.actor_id is None
    assert row.actor_display_name == ORCHESTRATOR_DISPLAY_NAME


def test_decorate_row_deleted_actor_renders_substitute() -> None:
    row = decorate_row(
        _record(facilitator_id=DELETED_ID),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
    )
    assert row.actor_id == DELETED_ID
    assert row.actor_display_name.startswith("<deleted-participant ")


# ---------------------------------------------------------------------------
# row_to_payload / page_to_payload
# ---------------------------------------------------------------------------


def test_row_to_payload_shape_matches_contract() -> None:
    row = decorate_row(_record(), session_id=SESSION_ID, name_by_id=NAME_BY_ID)
    payload = row_to_payload(row)
    expected_keys = {
        "id",
        "timestamp",
        "actor_id",
        "actor_display_name",
        "action",
        "action_label",
        "target_id",
        "target_display_name",
        "previous_value",
        "new_value",
        "summary",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["timestamp"] == "2026-05-08T14:30:00.000Z"
    assert payload["action_label"] == "Facilitator removed participant"


def test_row_to_payload_naive_timestamp_coerced_to_utc() -> None:
    """Legacy admin_audit_log rows used TIMESTAMP (no tz) — coerce to UTC."""
    naive = datetime(2026, 5, 8, 14, 30, 0)
    row = decorate_row(
        _record(timestamp=naive),
        session_id=SESSION_ID,
        name_by_id=NAME_BY_ID,
    )
    payload = row_to_payload(row)
    assert payload["timestamp"] == "2026-05-08T14:30:00.000Z"


def test_page_to_payload_includes_pagination_metadata() -> None:
    row = decorate_row(_record(), session_id=SESSION_ID, name_by_id=NAME_BY_ID)
    page = AuditLogPage(rows=[row], total_count=42, next_offset=1)
    body = page_to_payload(page)
    assert body["total_count"] == 42
    assert body["next_offset"] == 1
    assert len(body["rows"]) == 1
    assert body["rows"][0]["action"] == "remove_participant"
