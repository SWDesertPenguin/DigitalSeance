# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 audit-log WS broadcast helper coverage.

Covers ``broadcast_audit_log_appended`` and the ``log_admin_action``
``broadcast_session_id`` opt-in (T023):

- broadcast helper produces the spec 029 ``audit_log_appended`` envelope
- broadcast helper applies server-side scrub for ``scrub_value=True``
  actions (FR-014 defense in depth)
- broadcast helper restricts the role-filter to the facilitator role
- broadcast helper SWALLOWS broadcast-layer failures so the durable
  INSERT cannot be aborted by a WS error (durability invariant)
- ``log_admin_action(..., broadcast_session_id=...)`` fires the helper

These tests stub ``broadcast_to_session_roles`` with a small recorder so
no real WebSocket layer is exercised; only the helper's contract shape
is validated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.models.logs import AdminAuditLog
from src.repositories.log_repo import (
    LogRepository,
    broadcast_audit_log_appended,
)

SESSION_ID = "session-uuid-aaa"
FACILITATOR_ID = "alice-uuid-1234abcd"
TARGET_ID = "bob-uuid-5678efgh"


def _make_entry(action: str = "remove_participant") -> AdminAuditLog:
    """Build an in-memory AdminAuditLog row matching the asyncpg shape."""
    return AdminAuditLog(
        id=42,
        session_id=SESSION_ID,
        timestamp=datetime(2026, 5, 8, 14, 30, 0, tzinfo=UTC),
        facilitator_id=FACILITATOR_ID,
        action=action,
        target_id=TARGET_ID,
        previous_value="active",
        new_value="removed",
    )


class _BroadcastRecorder:
    """Captures broadcast calls so the test can assert on them."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        session_id: str,
        message: dict[str, Any],
        *,
        allow_roles: frozenset[str],
    ) -> None:
        self.calls.append(
            {
                "session_id": session_id,
                "message": message,
                "allow_roles": allow_roles,
            }
        )


# ---------------------------------------------------------------------------
# broadcast_audit_log_appended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_emits_audit_log_appended_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _BroadcastRecorder()
    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", recorder)
    entry = _make_entry()

    await broadcast_audit_log_appended(
        session_id=SESSION_ID,
        entry=entry,
        name_by_id={FACILITATOR_ID: "Alice", TARGET_ID: "Bob"},
    )

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["session_id"] == SESSION_ID
    assert call["message"]["v"] == 1
    assert call["message"]["type"] == "audit_log_appended"
    payload = call["message"]["payload"]
    assert payload["action"] == "remove_participant"
    assert payload["actor_display_name"] == "Alice"
    assert payload["target_display_name"] == "Bob"
    assert payload["previous_value"] == "active"
    assert payload["new_value"] == "removed"


@pytest.mark.asyncio
async def test_broadcast_applies_scrub_for_sensitive_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rotate_token / revoke_token rows ship as [scrubbed] over WS (FR-014)."""
    recorder = _BroadcastRecorder()
    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", recorder)
    entry = _make_entry(action="rotate_token")

    await broadcast_audit_log_appended(
        session_id=SESSION_ID,
        entry=entry,
        name_by_id={FACILITATOR_ID: "Alice", TARGET_ID: "Bob"},
    )

    payload = recorder.calls[0]["message"]["payload"]
    assert payload["previous_value"] == "[scrubbed]"
    assert payload["new_value"] == "[scrubbed]"


@pytest.mark.asyncio
async def test_broadcast_role_filtered_to_facilitator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The role-filter restricts delivery to facilitator subscribers only."""
    recorder = _BroadcastRecorder()
    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", recorder)

    await broadcast_audit_log_appended(
        session_id=SESSION_ID,
        entry=_make_entry(),
        name_by_id={},
    )

    assert recorder.calls[0]["allow_roles"] == frozenset({"facilitator"})


@pytest.mark.asyncio
async def test_broadcast_swallows_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broadcast-layer error MUST NOT propagate (durability invariant)."""

    async def _raise(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("ws layer down")

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", _raise)

    # MUST NOT raise — the helper's whole point is to absorb broadcast failures.
    await broadcast_audit_log_appended(
        session_id=SESSION_ID,
        entry=_make_entry(),
        name_by_id={},
    )


# ---------------------------------------------------------------------------
# log_admin_action(..., broadcast_session_id=...) opt-in (T023)
# ---------------------------------------------------------------------------


class _StubLogRepository(LogRepository):
    """Repo that bypasses the asyncpg pool for unit-only coverage."""

    def __init__(self) -> None:  # noqa: D401 — test stub
        self._pool = None  # type: ignore[assignment]
        self._inserted_record: dict[str, Any] | None = None
        self._name_map: dict[str, str] = {FACILITATOR_ID: "Alice", TARGET_ID: "Bob"}

    async def _fetch_one(self, query: str, *args: Any) -> dict[str, Any]:
        # log_admin_action calls _fetch_one once with the INSERT.
        self._inserted_record = {
            "id": 99,
            "session_id": args[0],
            "timestamp": datetime(2026, 5, 8, 14, 30, 0, tzinfo=UTC),
            "facilitator_id": args[1],
            "action": args[2],
            "target_id": args[3],
            "previous_value": args[4],
            "new_value": args[5],
        }
        return self._inserted_record  # type: ignore[return-value]

    async def _fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        return [{"id": pid, "display_name": name} for pid, name in self._name_map.items()]


@pytest.mark.asyncio
async def test_log_admin_action_no_broadcast_when_session_id_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default behavior: no spec 029 broadcast unless opted in."""
    audit_recorder = _BroadcastRecorder()
    legacy_recorder = _BroadcastRecorder()
    monkeypatch.setattr(
        "src.web_ui.websocket.broadcast_to_session_roles",
        legacy_recorder,
    )
    # The new helper imports from the same module, so both records share the recorder.
    repo = _StubLogRepository()

    await repo.log_admin_action(
        session_id=SESSION_ID,
        facilitator_id=FACILITATOR_ID,
        action="remove_participant",
        target_id=TARGET_ID,
        previous_value="active",
        new_value="removed",
    )

    types = [c["message"]["type"] for c in legacy_recorder.calls]
    assert "audit_entry" in types  # legacy push always fires
    assert "audit_log_appended" not in types  # new push only when opted in
    _ = audit_recorder  # silence unused warning


@pytest.mark.asyncio
async def test_log_admin_action_emits_spec029_event_when_opted_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """broadcast_session_id=<id> fires both legacy and spec 029 events."""
    recorder = _BroadcastRecorder()
    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", recorder)
    repo = _StubLogRepository()

    await repo.log_admin_action(
        session_id=SESSION_ID,
        facilitator_id=FACILITATOR_ID,
        action="remove_participant",
        target_id=TARGET_ID,
        previous_value="active",
        new_value="removed",
        broadcast_session_id=SESSION_ID,
    )

    types = [c["message"]["type"] for c in recorder.calls]
    assert "audit_entry" in types
    assert "audit_log_appended" in types
    spec029_call = next(c for c in recorder.calls if c["message"]["type"] == "audit_log_appended")
    assert spec029_call["allow_roles"] == frozenset({"facilitator"})
    payload = spec029_call["message"]["payload"]
    assert payload["action"] == "remove_participant"
    assert payload["actor_display_name"] == "Alice"
