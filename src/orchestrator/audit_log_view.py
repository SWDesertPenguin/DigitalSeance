# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read-side projections for the spec 029 audit log viewer.

Defines the ``AuditLogRow`` and ``AuditLogPage`` dataclasses (per
``specs/029-audit-log-viewer/data-model.md``) plus the row-decoration
helpers that map raw ``admin_audit_log`` records to facilitator-visible
projections:

- ``decorate_row(...)`` applies action-label registry lookup, server-side
  scrubbing (FR-014), display-name resolution (orchestrator / deleted /
  participant lookup), and timestamp formatting via the spec 029 paired
  ``audit_labels`` and ``time_format`` modules.
- ``row_to_payload(...)`` flattens a decorated row to the JSON-safe dict
  shipped by the FR-001 endpoint and the FR-010 WS event payload.

Pure helpers — no DB access, no HTTP, no WS. All I/O sits in
``src/repositories/log_repo.py`` and the route module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.orchestrator.audit_labels import format_label, is_scrub_value
from src.orchestrator.time_format import format_iso

ORCHESTRATOR_DISPLAY_NAME = "Orchestrator"
"""Static display name for orchestrator-actor rows (actor_id is null).

The label is intentionally static for v1 — research.md §11 defers an
env-var override to a future iteration.
"""

SCRUBBED_PLACEHOLDER = "[scrubbed]"
"""Literal string substituted for previous_value / new_value when the action's
registry entry has ``scrub_value=True``. Server-side defense per FR-014."""


@dataclass(frozen=True)
class AuditLogRow:
    """Decorated audit-log row for the FR-001 endpoint and FR-010 WS payload."""

    id: int
    timestamp: datetime
    actor_id: str | None
    actor_display_name: str
    action: str
    action_label: str
    target_id: str | None
    target_display_name: str | None
    previous_value: str | None
    new_value: str | None
    summary: str | None


@dataclass(frozen=True)
class AuditLogPage:
    """Paginated audit-log projection."""

    rows: list[AuditLogRow]
    total_count: int
    next_offset: int | None


def resolve_display_name(
    actor_id: str | None,
    name_by_id: dict[str, str],
) -> str:
    """Return the orchestrator-or-participant display name for an audit actor.

    - ``actor_id is None`` -> ``"Orchestrator"`` (system action).
    - ``actor_id`` resolves via ``name_by_id`` JOIN -> participant display name.
    - ``actor_id`` set but not in ``name_by_id`` -> deleted-participant
      substitute ``<deleted-participant <short_id>>`` per research.md §11.
    """
    if actor_id is None:
        return ORCHESTRATOR_DISPLAY_NAME
    name = name_by_id.get(actor_id)
    if name is not None:
        return name
    short = actor_id[:8] if actor_id else "unknown"
    return f"<deleted-participant {short}>"


def resolve_target_display_name(
    target_id: str | None,
    session_id: str,
    name_by_id: dict[str, str],
) -> str | None:
    """Return the target display name, or ``None`` for session-scoped actions.

    When ``target_id == session_id`` the action targets the session itself
    (e.g., ``cap_set``, ``session_config_change``, every spec 014 mode_*
    row), so the field is ``None``. When ``target_id`` resolves via JOIN it
    returns the participant's display name; otherwise the deleted-participant
    substitute.
    """
    if target_id is None or target_id == session_id:
        return None
    name = name_by_id.get(target_id)
    if name is not None:
        return name
    short = target_id[:8] if target_id else "unknown"
    return f"<deleted-participant {short}>"


def _resolve_actor_id(
    facilitator_id: str | None,
    orchestrator_actor_ids: frozenset[str] | None,
) -> str | None:
    """Map the raw audit-row facilitator_id to actor_id with sentinel handling."""
    if (
        orchestrator_actor_ids is not None
        and facilitator_id is not None
        and facilitator_id in orchestrator_actor_ids
    ):
        return None
    return facilitator_id


def _apply_scrub(
    action: str,
    previous_value: str | None,
    new_value: str | None,
) -> tuple[str | None, str | None]:
    """Substitute SCRUBBED_PLACEHOLDER per FR-014; nulls pass through."""
    if not is_scrub_value(action):
        return previous_value, new_value
    prev_out = SCRUBBED_PLACEHOLDER if previous_value is not None else None
    new_out = SCRUBBED_PLACEHOLDER if new_value is not None else None
    return prev_out, new_out


def decorate_row(
    record: dict[str, Any],
    *,
    session_id: str,
    name_by_id: dict[str, str],
    orchestrator_actor_ids: frozenset[str] | None = None,
) -> AuditLogRow:
    """Map a raw ``admin_audit_log`` row to its decorated projection.

    The ``orchestrator_actor_ids`` set names actor IDs that should be
    rendered as "Orchestrator" even though their actor_id is non-null
    (e.g., spec 014 mode_* rows that pass ``facilitator_id=session_id``).
    Server-side scrubbing applies BEFORE the row leaves this helper per
    FR-014: when the registry entry has ``scrub_value=True``, both
    ``previous_value`` and ``new_value`` ship as ``"[scrubbed]"``.
    """
    actor_id = _resolve_actor_id(record.get("facilitator_id"), orchestrator_actor_ids)
    raw_action = str(record["action"])
    target_id = record.get("target_id")
    previous_value, new_value = _apply_scrub(
        raw_action, record.get("previous_value"), record.get("new_value")
    )
    return AuditLogRow(
        id=int(record["id"]),
        timestamp=record["timestamp"],
        actor_id=actor_id,
        actor_display_name=resolve_display_name(actor_id, name_by_id),
        action=raw_action,
        action_label=format_label(raw_action),
        target_id=target_id,
        target_display_name=resolve_target_display_name(target_id, session_id, name_by_id),
        previous_value=previous_value,
        new_value=new_value,
        summary=record.get("summary"),
    )


def row_to_payload(row: AuditLogRow) -> dict[str, Any]:
    """Flatten an ``AuditLogRow`` to the JSON-safe payload shape.

    The output matches the schema in ``contracts/audit-log-endpoint.md``
    and ``contracts/ws-events.md`` (identical row shape on both surfaces).
    Timestamp uses the spec 029 paired ``format_iso`` for parity with the
    frontend ``formatIso`` mirror.
    """
    timestamp = row.timestamp
    if timestamp is not None and timestamp.tzinfo is None:
        # Pre-013 admin_audit_log used TIMESTAMP (no tz); coerce to UTC for
        # the formatter contract. Constitutional/V14 timestamps SHOULD be
        # tz-aware going forward, but legacy rows still exist.
        from datetime import UTC

        timestamp = timestamp.replace(tzinfo=UTC)
    return {
        "id": str(row.id),
        "timestamp": format_iso(timestamp) if timestamp is not None else None,
        "actor_id": row.actor_id,
        "actor_display_name": row.actor_display_name,
        "action": row.action,
        "action_label": row.action_label,
        "target_id": row.target_id,
        "target_display_name": row.target_display_name,
        "previous_value": row.previous_value,
        "new_value": row.new_value,
        "summary": row.summary,
    }


def page_to_payload(page: AuditLogPage) -> dict[str, Any]:
    """Flatten an ``AuditLogPage`` to the JSON-safe response body."""
    return {
        "rows": [row_to_payload(r) for r in page.rows],
        "total_count": page.total_count,
        "next_offset": page.next_offset,
    }
