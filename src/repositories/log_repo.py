"""Log repository — append-only operational logs.

No update or delete methods. Append-only enforced by interface.
"""

from __future__ import annotations

from src.models.logs import AdminAuditLog, ConvergenceLog, RoutingLog, UsageLog
from src.repositories.base import BaseRepository


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
    ) -> RoutingLog:
        """Append a routing decision log entry."""
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
        """Fetch recent convergence measurements."""
        rows = await self._fetch_all(
            _CONVERGENCE_WINDOW_SQL,
            session_id,
            window_size,
        )
        return [ConvergenceLog.from_record(r) for r in reversed(rows)]

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
        """Append a facilitator action record."""
        record = await self._fetch_one(
            _INSERT_AUDIT_SQL,
            session_id,
            facilitator_id,
            action,
            target_id,
            previous_value,
            new_value,
        )
        return AdminAuditLog.from_record(record)

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


# --- SQL Constants ---

_INSERT_ROUTING_SQL = """
    INSERT INTO routing_log
        (session_id, turn_number, intended_participant,
         actual_participant, routing_action,
         complexity_score, domain_match, reason)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
    ORDER BY turn_number DESC LIMIT $2
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
