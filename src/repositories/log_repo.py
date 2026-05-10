# SPDX-License-Identifier: AGPL-3.0-or-later

"""Log repository — append-only operational logs.

No update or delete methods. Append-only enforced by interface.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from src.models.logs import AdminAuditLog, ConvergenceLog, RoutingLog, SecurityEvent, UsageLog
from src.repositories.base import BaseRepository

if TYPE_CHECKING:
    from src.orchestrator.audit_log_view import AuditLogPage


class LogRepository(BaseRepository):
    """Data access for all four append-only log types."""

    # --- Routing Log ---

    async def log_routing(
        self,
        *,
        session_id: str,
        turn_number: int,
        intended: str,
        actual: str,
        action: str,
        complexity: str,
        domain_match: bool,
        reason: str,
        route_ms: int | None = None,
        assemble_ms: int | None = None,
        dispatch_ms: int | None = None,
        persist_ms: int | None = None,
        advisory_lock_wait_ms: int | None = None,
        shaping_score_ms: int | None = None,
        shaping_retry_dispatch_ms: int | None = None,
        filler_score: float | None = None,
        shaping_retry_delta_text: str | None = None,
        shaping_reason: str | None = None,
    ) -> RoutingLog:
        """Append a routing decision log entry.

        Per-stage timing columns (route_ms..advisory_lock_wait_ms) back
        Constitution §12 V14 / 003 §FR-030 + §FR-032; populated by the
        turn-loop persist path (012 US6) and remain NULL on skip-path
        / pre-instrumentation rows.

        Spec 021 (T031): the five shaping columns
        (``shaping_score_ms``..``shaping_reason``) are NULL on every row
        when ``SACP_RESPONSE_SHAPING_ENABLED`` is off (SC-002 byte-equal)
        and on skip-path rows. When shaping is on, the loop wiring (T029)
        populates ``shaping_score_ms`` + ``filler_score`` on every
        evaluation, ``shaping_retry_dispatch_ms`` +
        ``shaping_retry_delta_text`` on each per-retry row, and
        ``shaping_reason`` per FR-011 (one of ``'filler_retry'`` /
        ``'filler_retry_exhausted'`` /
        ``'compound_retry_exhausted'`` / ``'shaping_pipeline_error'``).
        """
        record = await self._fetch_one(
            _INSERT_ROUTING_SQL,
            session_id,
            turn_number,
            intended,
            actual,
            action,
            complexity,
            domain_match,
            reason,
            route_ms,
            assemble_ms,
            dispatch_ms,
            persist_ms,
            advisory_lock_wait_ms,
            shaping_score_ms,
            shaping_retry_dispatch_ms,
            filler_score,
            shaping_retry_delta_text,
            shaping_reason,
        )
        return RoutingLog.from_record(record)

    async def get_routing_history(
        self,
        session_id: str,
        *,
        limit: int = 100,
    ) -> list[RoutingLog]:
        """Fetch routing history for a session."""
        rows = await self._fetch_all(
            _ROUTING_HISTORY_SQL,
            session_id,
            limit,
        )
        return [RoutingLog.from_record(r) for r in rows]

    # --- Usage Log ---

    async def log_usage(
        self,
        *,
        participant_id: str,
        turn_number: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> UsageLog:
        """Append a token usage log entry."""
        record = await self._fetch_one(
            _INSERT_USAGE_SQL,
            participant_id,
            turn_number,
            input_tokens,
            output_tokens,
            cost_usd,
        )
        return UsageLog.from_record(record)

    async def get_participant_usage(
        self,
        participant_id: str,
    ) -> list[UsageLog]:
        """Fetch all usage entries for a participant."""
        rows = await self._fetch_all(
            _PARTICIPANT_USAGE_SQL,
            participant_id,
        )
        return [UsageLog.from_record(r) for r in rows]

    async def get_participant_cost(
        self,
        participant_id: str,
        *,
        period: str = "daily",
    ) -> float:
        """Aggregate cost for budget enforcement."""
        sql = _COST_DAILY_SQL if period == "daily" else _COST_HOURLY_SQL
        result = await self._fetch_one(sql, participant_id)
        return float(result["total"]) if result and result["total"] else 0.0

    # --- Convergence Log ---

    async def log_convergence(
        self,
        *,
        turn_number: int,
        session_id: str,
        embedding: bytes,
        similarity_score: float,
        divergence_prompted: bool = False,
    ) -> ConvergenceLog:
        """Append a convergence measurement."""
        record = await self._fetch_one(
            _INSERT_CONVERGENCE_SQL,
            turn_number,
            session_id,
            embedding,
            similarity_score,
            divergence_prompted,
        )
        return ConvergenceLog.from_record(record)

    async def get_convergence_window(
        self,
        session_id: str,
        window_size: int,
    ) -> list[ConvergenceLog]:
        """Fetch recent convergence measurements (tier='convergence' only).

        density-anomaly rows (tier='density_anomaly', spec 004 §FR-020)
        live in the same table but are filtered out here so the embedding
        sliding window only sees actual convergence measurements.
        """
        rows = await self._fetch_all(
            _CONVERGENCE_WINDOW_SQL,
            session_id,
            window_size,
        )
        return [ConvergenceLog.from_record(r) for r in reversed(rows)]

    async def log_density_anomaly(
        self,
        *,
        turn_number: int,
        session_id: str,
        density_value: float,
        baseline_value: float,
    ) -> None:
        """Append a density-anomaly row to convergence_log.

        Spec 004 §FR-020: Phase 1 observational signal, no escalation
        action. embedding + similarity_score stay NULL (this turn's
        embedding lives on the sibling tier='convergence' row).
        """
        await self._execute(
            _INSERT_DENSITY_ANOMALY_SQL,
            turn_number,
            session_id,
            density_value,
            baseline_value,
        )

    # --- Admin Audit Log ---

    async def log_admin_action(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        action: str,
        target_id: str,
        previous_value: str | None = None,
        new_value: str | None = None,
    ) -> AdminAuditLog:
        """Append a facilitator action record and fan out a WS audit_entry."""
        record = await self._fetch_one(
            _INSERT_AUDIT_SQL,
            session_id,
            facilitator_id,
            action,
            target_id,
            previous_value,
            new_value,
        )
        entry = AdminAuditLog.from_record(record)
        await _broadcast_audit_entry(entry)
        return entry

    async def get_audit_log(
        self,
        session_id: str,
    ) -> list[AdminAuditLog]:
        """Fetch all audit entries for a session."""
        rows = await self._fetch_all(
            _AUDIT_LOG_SQL,
            session_id,
        )
        return [AdminAuditLog.from_record(r) for r in rows]

    async def _fetch_audit_page_raw(
        self,
        session_id: str,
        offset: int,
        limit: int,
        retention_days: int | None,
    ) -> tuple[list, int]:
        """Run the page + count SQL pair; returns (raw_rows, total_count)."""
        if retention_days is not None and retention_days > 0:
            rows_sql = _AUDIT_LOG_PAGE_RETENTION_SQL
            count_sql = _AUDIT_LOG_COUNT_RETENTION_SQL
            raw_rows = await self._fetch_all(rows_sql, session_id, retention_days, limit, offset)
            count_record = await self._fetch_one(count_sql, session_id, retention_days)
        else:
            raw_rows = await self._fetch_all(_AUDIT_LOG_PAGE_SQL, session_id, limit, offset)
            count_record = await self._fetch_one(_AUDIT_LOG_COUNT_SQL, session_id)
        total_count = int(count_record["total"]) if count_record else 0
        return raw_rows, total_count

    async def _load_session_name_map(self, session_id: str) -> dict[str, str]:
        """Build a per-session participant id -> display_name lookup."""
        participant_rows = await self._fetch_all(
            "SELECT id, display_name FROM participants WHERE session_id = $1",
            session_id,
        )
        return {r["id"]: r["display_name"] for r in participant_rows}

    async def get_audit_log_page(
        self,
        session_id: str,
        *,
        offset: int,
        limit: int,
        retention_days: int | None = None,
    ) -> AuditLogPage:
        """Paginated, decorated audit-log page for the FR-001 endpoint (spec 029).

        The covering index on ``(session_id, timestamp DESC)`` (alembic 013)
        supports both the rows page and the parallel COUNT(*). Display-name
        JOINs run in Python (audit rows use TEXT identifiers with no FK;
        deleted-participant rows still need to render). Per FR-014 the
        decoration step applies server-side scrubbing before rows leave.
        """
        from src.orchestrator.audit_log_view import AuditLogPage, decorate_row

        raw_rows, total_count = await self._fetch_audit_page_raw(
            session_id, offset, limit, retention_days
        )
        name_by_id = await self._load_session_name_map(session_id)
        decorated = [
            decorate_row(dict(r), session_id=session_id, name_by_id=name_by_id) for r in raw_rows
        ]
        rendered = offset + len(decorated)
        next_offset = rendered if rendered < total_count else None
        return AuditLogPage(rows=decorated, total_count=total_count, next_offset=next_offset)

    # --- Spec 021 register-change audit-event helpers ---
    # Three new ``action`` strings reuse the existing admin_audit_log table
    # (no schema change). See specs/021-ai-response-shaping/contracts/
    # audit-events.md for row-level field semantics.

    async def log_register_change(
        self,
        *,
        action: Literal[
            "session_register_changed",
            "participant_register_override_set",
            "participant_register_override_cleared",
        ],
        session_id: str,
        target_id: str,
        previous_value: dict[str, Any] | None,
        new_value: dict[str, Any],
        facilitator_id: str,
    ) -> AdminAuditLog:
        """Append a register-change audit row.

        Spec 021 T043. Wraps ``log_admin_action`` so callers in
        ``src.mcp_server.tools.facilitator`` (T040 / T052) hand structured
        dicts and the helper renders them as JSON for the audit row's
        TEXT columns. ``previous_value`` is ``None`` on a first-time set
        (no prior row existed) per the contract.

        Cascade-induced clears (participant or session removed) MUST NOT
        route through this helper — the parent delete event suffices per
        FR-015 + research.md §8. Only explicit facilitator-action set /
        update / clear paths emit a register-change audit row.
        """
        previous_payload = json.dumps(previous_value) if previous_value is not None else None
        new_payload = json.dumps(new_value)
        return await self.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action=action,
            target_id=target_id,
            previous_value=previous_payload,
            new_value=new_payload,
        )

    # --- Spec 014 mode_* audit-event helpers (DMA controller) ---
    # Five new ``action`` strings reuse the existing admin_audit_log table
    # (no schema change). See specs/014-dynamic-mode-assignment/contracts/
    # audit-events.md for row-level field semantics.

    async def log_mode_recommendation(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        previous_action: str | None,
        action: str,
        triggers: list[str],
        signal_observations: list[dict[str, Any]],
        dwell_floor_at: datetime | None,
    ) -> AdminAuditLog:
        """Append a ``mode_recommendation`` row (014 §FR-005).

        Fires in BOTH advisory and auto-apply modes whenever the controller's
        decision differs from ``ControllerState.last_emitted_action``.
        ``target_id`` is the session_id (the audit row's subject is the
        session, not a participant).
        """
        previous_value = (
            json.dumps({"action": previous_action}) if previous_action is not None else None
        )
        new_value = json.dumps(
            {
                "action": action,
                "triggers": triggers,
                "signal_observations": signal_observations,
                "dwell_floor_at": _iso_or_none(dwell_floor_at),
            }
        )
        return await self.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="mode_recommendation",
            target_id=session_id,
            previous_value=previous_value,
            new_value=new_value,
        )

    async def log_mode_transition(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        previous_action: str | None,
        action: str,
        triggers: list[str],
        signal_observations: list[dict[str, Any]],
        engaged_mechanisms: list[str],
        skipped_mechanisms: list[str],
        dwell_floor_at: datetime | None,
    ) -> AdminAuditLog:
        """Append a ``mode_transition`` row (014 §FR-006).

        Pairs with ``mode_recommendation`` at the same ``decision_at``;
        operators JOIN on ``(target_id, timestamp)`` to trace recommendation
        through to transition.
        """
        previous_value = json.dumps(
            {"action": previous_action, "engaged_mechanisms": engaged_mechanisms}
        )
        new_value = json.dumps(
            {
                "action": action,
                "triggers": triggers,
                "signal_observations": signal_observations,
                "engaged_mechanisms": engaged_mechanisms,
                "skipped_mechanisms": skipped_mechanisms,
                "dwell_floor_at": _iso_or_none(dwell_floor_at),
            }
        )
        return await self.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="mode_transition",
            target_id=session_id,
            previous_value=previous_value,
            new_value=new_value,
        )

    async def log_mode_transition_suppressed(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        current_action: str | None,
        would_have_fired: str,
        eligible_at: datetime,
    ) -> AdminAuditLog:
        """Append a ``mode_transition_suppressed`` row (014 §FR-008).

        Emitted when auto-apply would have fired a transition but the dwell
        floor blocked it. ``reason`` is fixed to ``"dwell_floor_not_reached"``
        in Phase 3 — reserved for future reasons per data-model.md.
        """
        previous_value = json.dumps({"current_action": current_action})
        new_value = json.dumps(
            {
                "would_have_fired": would_have_fired,
                "reason": "dwell_floor_not_reached",
                "eligible_at": _iso_or_none(eligible_at),
            }
        )
        return await self.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="mode_transition_suppressed",
            target_id=session_id,
            previous_value=previous_value,
            new_value=new_value,
        )

    async def log_decision_cycle_throttled(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        cap_per_minute: int,
        last_cycle_at: datetime | None,
        next_eligible_at: datetime,
    ) -> AdminAuditLog:
        """Append a ``decision_cycle_throttled`` row (014 §FR-002 + FR-013).

        Rate-limited per FR-013: at most one row per dwell window per session.
        The caller (``DmaController._maybe_emit_throttled``) enforces the
        rate limit; this helper is the single audit-write point.
        """
        previous_value = json.dumps(
            {"cap_per_minute": cap_per_minute, "last_cycle_at": _iso_or_none(last_cycle_at)}
        )
        new_value = json.dumps(
            {
                "reason": "rate_cap_exceeded",
                "next_eligible_at": _iso_or_none(next_eligible_at),
            }
        )
        return await self.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="decision_cycle_throttled",
            target_id=session_id,
            previous_value=previous_value,
            new_value=new_value,
        )

    async def log_signal_source_unavailable(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        signal_name: str,
        last_known_state: str,
        since: datetime,
        rate_limited_until: datetime,
    ) -> AdminAuditLog:
        """Append a ``signal_source_unavailable`` row (014 §FR-013).

        Rate-limited per FR-013: at most one row per dwell window per signal
        per session. The caller enforces the rate limit; this helper is the
        single audit-write point.
        """
        previous_value = json.dumps({"signal": signal_name, "last_known_state": last_known_state})
        new_value = json.dumps(
            {
                "signal": signal_name,
                "since": _iso_or_none(since),
                "rate_limited_until": _iso_or_none(rate_limited_until),
            }
        )
        return await self.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="signal_source_unavailable",
            target_id=session_id,
            previous_value=previous_value,
            new_value=new_value,
        )

    # --- Security Events ---

    async def log_security_event(
        self,
        *,
        session_id: str,
        speaker_id: str,
        turn_number: int,
        layer: str,
        findings: str,
        risk_score: float | None = None,
        blocked: bool = False,
        layer_duration_ms: int | None = None,
        override_reason: str | None = None,
        override_actor_id: str | None = None,
    ) -> SecurityEvent:
        """Append a security pipeline detection record (CHK008).

        ``layer_duration_ms`` records the wall-clock time the named
        layer spent inspecting the response (007 §FR-020).

        ``override_reason`` and ``override_actor_id`` are populated
        only when ``layer='facilitator_override'`` (spec 012 FR-006
        §4.9 approach (b)): a facilitator explicitly approved a draft
        that re-flagged the pipeline.
        """
        record = await self._fetch_one(
            _INSERT_SECURITY_EVENT_SQL,
            session_id,
            speaker_id,
            turn_number,
            layer,
            risk_score,
            findings,
            blocked,
            layer_duration_ms,
            override_reason,
            override_actor_id,
        )
        return SecurityEvent.from_record(record)

    async def get_security_events(
        self,
        session_id: str,
    ) -> list[SecurityEvent]:
        """Fetch all security events for a session in chronological order."""
        rows = await self._fetch_all(_SECURITY_EVENTS_SQL, session_id)
        return [SecurityEvent.from_record(r) for r in rows]


def _iso_or_none(value: datetime | None) -> str | None:
    """Render a datetime as ISO-8601, or pass through None.

    Spec 014 helper: every mode_* audit row payload field that names a
    timestamp uses this for consistent JSON encoding.
    """
    return value.isoformat() if value is not None else None


def _entry_to_record(entry: AdminAuditLog) -> dict[str, Any]:
    """Project an ``AdminAuditLog`` row to the dict shape ``decorate_row`` expects."""
    return {
        "id": entry.id,
        "timestamp": entry.timestamp,
        "facilitator_id": entry.facilitator_id,
        "action": entry.action,
        "target_id": entry.target_id,
        "previous_value": entry.previous_value,
        "new_value": entry.new_value,
    }


async def broadcast_audit_log_appended(
    *,
    session_id: str,
    entry: AdminAuditLog,
    name_by_id: dict[str, str] | None = None,
    orchestrator_actor_ids: frozenset[str] | None = None,
) -> None:
    """Push the spec 029 ``audit_log_appended`` WS event to facilitators.

    Wraps every failure mode so the call site cannot abort the underlying
    INSERT — the durable record is authoritative; the live push is
    best-effort. Per ``contracts/ws-events.md`` and FR-014 the payload
    carries the server-scrubbed row shape. Late-imports the web_ui layer
    so repositories stay decoupled at import time.
    """
    import logging

    log = logging.getLogger(__name__)
    try:
        from src.orchestrator.audit_log_view import decorate_row, row_to_payload
        from src.web_ui.events import audit_log_appended_event
        from src.web_ui.websocket import broadcast_to_session_roles

        decorated = decorate_row(
            _entry_to_record(entry),
            session_id=session_id,
            name_by_id=name_by_id or {},
            orchestrator_actor_ids=orchestrator_actor_ids,
        )
        await broadcast_to_session_roles(
            session_id,
            audit_log_appended_event(row_to_payload(decorated)),
            allow_roles=frozenset({"facilitator"}),
        )
    except Exception:  # noqa: BLE001 — durability invariant (durable record wins)
        log.exception(
            "audit_log_appended broadcast failed session_id=%s action=%s",
            session_id,
            entry.action,
        )


async def _broadcast_audit_entry(entry: AdminAuditLog) -> None:
    """Push an audit_entry WS event to facilitators only.

    Audit-entry payloads carry full ``previous_value`` / ``new_value``
    bodies — for ``review_gate_edit`` that's the entire edited draft;
    for ``set_budget`` it's currency caps; for ``reject_participant``
    it's the rejection reason. Non-facilitators (including pending
    joiners and observers) have no business seeing those, so we
    filter the broadcast at send time. Facilitator-side AdminPanel
    UIs continue to see every entry.

    Late-imported so repositories stay decoupled from the web_ui layer
    at import time — call is a no-op when nothing is subscribed.
    """
    from src.web_ui.events import audit_entry_event
    from src.web_ui.websocket import broadcast_to_session_roles

    payload = {
        "id": entry.id,
        "facilitator_id": entry.facilitator_id,
        "action": entry.action,
        "target_id": entry.target_id,
        "previous_value": entry.previous_value,
        "new_value": entry.new_value,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
    }
    await broadcast_to_session_roles(
        entry.session_id,
        audit_entry_event(payload),
        allow_roles=frozenset({"facilitator"}),
    )


# --- SQL Constants ---

_INSERT_ROUTING_SQL = """
    INSERT INTO routing_log
        (session_id, turn_number, intended_participant,
         actual_participant, routing_action,
         complexity_score, domain_match, reason,
         route_ms, assemble_ms, dispatch_ms, persist_ms,
         advisory_lock_wait_ms,
         shaping_score_ms, shaping_retry_dispatch_ms,
         filler_score, shaping_retry_delta_text, shaping_reason)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
            $9, $10, $11, $12, $13,
            $14, $15, $16, $17, $18)
    RETURNING *
"""

_ROUTING_HISTORY_SQL = """
    SELECT * FROM routing_log
    WHERE session_id = $1
    ORDER BY turn_number DESC LIMIT $2
"""

_INSERT_USAGE_SQL = """
    INSERT INTO usage_log
        (participant_id, turn_number,
         input_tokens, output_tokens, cost_usd)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING *
"""

_PARTICIPANT_USAGE_SQL = """
    SELECT * FROM usage_log
    WHERE participant_id = $1
    ORDER BY timestamp
"""

_COST_DAILY_SQL = """
    SELECT COALESCE(SUM(cost_usd), 0) AS total
    FROM usage_log
    WHERE participant_id = $1
      AND timestamp >= NOW() - INTERVAL '1 day'
"""

_COST_HOURLY_SQL = """
    SELECT COALESCE(SUM(cost_usd), 0) AS total
    FROM usage_log
    WHERE participant_id = $1
      AND timestamp >= NOW() - INTERVAL '1 hour'
"""

_INSERT_CONVERGENCE_SQL = """
    INSERT INTO convergence_log
        (turn_number, session_id, embedding, similarity_score, divergence_prompted)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING *
"""

_CONVERGENCE_WINDOW_SQL = """
    SELECT * FROM convergence_log
    WHERE session_id = $1
      AND tier = 'convergence'
    ORDER BY turn_number DESC LIMIT $2
"""

_INSERT_DENSITY_ANOMALY_SQL = """
    INSERT INTO convergence_log
        (turn_number, session_id, tier, density_value, baseline_value)
    VALUES ($1, $2, 'density_anomaly', $3, $4)
    ON CONFLICT (turn_number, session_id, tier) DO NOTHING
"""

_INSERT_AUDIT_SQL = """
    INSERT INTO admin_audit_log
        (session_id, facilitator_id, action,
         target_id, previous_value, new_value)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *
"""

_AUDIT_LOG_SQL = """
    SELECT * FROM admin_audit_log
    WHERE session_id = $1
    ORDER BY timestamp
"""

# spec 029 FR-001 / FR-005 — paginated reverse-chronological page query.
# The covering index on (session_id, timestamp DESC) (alembic 013) supports
# this WHERE + ORDER + LIMIT plan.
_AUDIT_LOG_PAGE_SQL = """
    SELECT * FROM admin_audit_log
    WHERE session_id = $1
    ORDER BY timestamp DESC
    LIMIT $2 OFFSET $3
"""

_AUDIT_LOG_COUNT_SQL = """
    SELECT COUNT(*) AS total FROM admin_audit_log
    WHERE session_id = $1
"""

# spec 029 FR-016 — display-only retention cap. Postgres-side INTERVAL math
# parameterized via integer days; rejected at validator boundary so the
# value is always [1, 36500] when set.
_AUDIT_LOG_PAGE_RETENTION_SQL = """
    SELECT * FROM admin_audit_log
    WHERE session_id = $1
      AND timestamp >= NOW() - make_interval(days => $2)
    ORDER BY timestamp DESC
    LIMIT $3 OFFSET $4
"""

_AUDIT_LOG_COUNT_RETENTION_SQL = """
    SELECT COUNT(*) AS total FROM admin_audit_log
    WHERE session_id = $1
      AND timestamp >= NOW() - make_interval(days => $2)
"""

_INSERT_SECURITY_EVENT_SQL = """
    INSERT INTO security_events
        (session_id, speaker_id, turn_number, layer, risk_score, findings, blocked,
         layer_duration_ms, override_reason, override_actor_id)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING *
"""

_SECURITY_EVENTS_SQL = """
    SELECT * FROM security_events
    WHERE session_id = $1
    ORDER BY timestamp
"""
