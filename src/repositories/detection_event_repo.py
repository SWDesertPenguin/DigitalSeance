# SPDX-License-Identifier: AGPL-3.0-or-later

"""Detection-event repository (spec 022).

INSERT + disposition-transition operations against the dedicated
``detection_events`` table. Read operations live on
``LogRepository.get_detection_events_page`` (added in Sweep 2 T015) so
spec 010 debug-export and spec 022's panel surface share the same
read code path.

The disposition transition handler wraps the
``UPDATE detection_events SET disposition`` and the matching
``INSERT INTO admin_audit_log`` in a single transaction per
``data-model.md`` "Transition rows". A failure rolls back both halves.

The INSERT helper is intentionally a thin wrapper: dual-write call
sites (T019 sweep) call it once per detector fire alongside their
existing WS broadcast. INSERT failure does NOT block the existing
broadcast per the FR-017 fail-soft contract — callers handle the
exception and log a security-event.
"""

from __future__ import annotations

from typing import Literal

import asyncpg

# CHECK constraint vocabulary (alembic 017) — duplicated as a Literal
# so the type checker rejects out-of-range values at the call site.
EventClass = Literal[
    "ai_question_opened",
    "ai_exit_requested",
    "density_anomaly",
    "mode_recommendation",
    "mode_change",
]
Disposition = Literal[
    "pending",
    "banner_acknowledged",
    "banner_dismissed",
    "auto_resolved",
]


_INSERT_SQL = """
    INSERT INTO detection_events (
        session_id, event_class, participant_id,
        trigger_snippet, detector_score, turn_number
    ) VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id
"""


async def insert_detection_event(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    event_class: EventClass,
    participant_id: str,
    trigger_snippet: str | None = None,
    detector_score: float | None = None,
    turn_number: int | None = None,
) -> int:
    """Persist a new detection event and return its primary key id.

    Called from the four detector emit sites (T019 dual-write sweep).
    The CHECK constraint enforces ``event_class`` membership at the DB
    layer; passing an out-of-range value raises ``asyncpg.CheckViolation``
    which callers MUST NOT silently swallow.
    """
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            _INSERT_SQL,
            session_id,
            event_class,
            participant_id,
            trigger_snippet,
            detector_score,
            turn_number,
        )
        return int(row_id)


_TRANSITION_SQL = """
    UPDATE detection_events
       SET disposition = $1,
           last_disposition_change_at = NOW()
     WHERE id = $2
       AND session_id = $3
     RETURNING id
"""

_AUDIT_INSERT_SQL = """
    INSERT INTO admin_audit_log (
        session_id, facilitator_id, action, target_id
    ) VALUES ($1, $2, $3, $4)
    RETURNING id
"""


async def apply_disposition_transition(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    event_id: int,
    facilitator_id: str,
    new_disposition: Disposition,
    action: str,
) -> int:
    """Transition an event's disposition in one transaction.

    UPDATEs ``detection_events.disposition`` and INSERTs the
    corresponding ``admin_audit_log`` row atomically. Returns the new
    audit row id. Raises ``ValueError`` if ``event_id`` is not found in
    ``session_id`` (mismatch ⇒ refuse to write a stray audit row).

    ``action`` is one of:
    ``detection_event_acknowledged`` / ``detection_event_dismissed`` /
    ``detection_event_auto_resolved``. The re-surface action uses a
    separate helper (it does NOT update disposition; see
    ``apply_resurface``).
    """
    async with pool.acquire() as conn, conn.transaction():
        updated = await conn.fetchval(_TRANSITION_SQL, new_disposition, event_id, session_id)
        if updated is None:
            raise ValueError(f"detection_event {event_id} not found in session {session_id}")
        audit_id = await conn.fetchval(
            _AUDIT_INSERT_SQL,
            session_id,
            facilitator_id,
            action,
            str(event_id),
        )
        return int(audit_id)


async def apply_resurface(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    event_id: int,
    facilitator_id: str,
) -> int:
    """Append a ``detection_event_resurface`` audit row (no disposition change).

    Per Clarifications §2 + ``data-model.md`` "Transition rows", re-surface
    is operator-only and does NOT mutate the event's disposition; it
    only records the forensic trail. The WS rebroadcast happens
    separately via ``cross_instance_broadcast.broadcast_session_event``.
    """
    async with pool.acquire() as conn:
        # Verify the event exists in the session before writing the audit row,
        # so a malformed/cross-session POST cannot pollute admin_audit_log.
        exists = await conn.fetchval(
            "SELECT id FROM detection_events WHERE id = $1 AND session_id = $2",
            event_id,
            session_id,
        )
        if exists is None:
            raise ValueError(f"detection_event {event_id} not found in session {session_id}")
        audit_id = await conn.fetchval(
            _AUDIT_INSERT_SQL,
            session_id,
            facilitator_id,
            "detection_event_resurface",
            str(event_id),
        )
        return int(audit_id)
