"""Session and Branch repository — atomic creation, lifecycle queries."""

from __future__ import annotations

import uuid

import asyncpg

from src.models.participant import Participant
from src.models.session import Branch, Session
from src.repositories.base import BaseRepository
from src.repositories.errors import InvalidTransitionError


class SessionRepository(BaseRepository):
    """Data access for sessions, branches, and session-scoped queries."""

    async def create_session(
        self,
        name: str,
        *,
        facilitator_display_name: str,
        facilitator_provider: str,
        facilitator_model: str,
        facilitator_model_tier: str,
        facilitator_model_family: str,
        facilitator_context_window: int,
        facilitator_api_endpoint: str | None = None,
        review_gate_pause_scope: str = "session",
    ) -> tuple[Session, Participant, Branch]:
        """Atomically create session + facilitator + main branch."""
        ids = _generate_ids()
        async with self._pool.acquire() as conn, conn.transaction():
            await _insert_session(conn, ids["session"], name, review_gate_pause_scope)
            await _insert_facilitator(
                conn,
                participant_id=ids["facilitator"],
                session_id=ids["session"],
                display_name=facilitator_display_name,
                provider=facilitator_provider,
                model=facilitator_model,
                model_tier=facilitator_model_tier,
                model_family=facilitator_model_family,
                context_window=facilitator_context_window,
                api_endpoint=facilitator_api_endpoint,
            )
            await _link_facilitator(conn, ids["session"], ids["facilitator"])
            branch_id = f"main-{ids['session'][:8]}"
            await _insert_main_branch(conn, branch_id, ids["session"], ids["facilitator"])
            return await _fetch_created(conn, ids, branch_id)

    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID."""
        record = await self._fetch_one(
            "SELECT * FROM sessions WHERE id = $1",
            session_id,
        )
        return Session.from_record(record) if record else None

    async def list_sessions(
        self,
        *,
        status_filter: str | None = None,
    ) -> list[Session]:
        """List sessions, optionally filtered by status."""
        if status_filter:
            rows = await self._fetch_all(
                "SELECT * FROM sessions WHERE status = $1 ORDER BY created_at DESC",
                status_filter,
            )
        else:
            rows = await self._fetch_all(
                "SELECT * FROM sessions ORDER BY created_at DESC",
            )
        return [Session.from_record(r) for r in rows]

    async def update_facilitator(
        self,
        session_id: str,
        new_facilitator_id: str,
    ) -> None:
        """Update the session's facilitator reference."""
        await self._execute(
            "UPDATE sessions SET facilitator_id = $1 WHERE id = $2",
            new_facilitator_id,
            session_id,
        )

    async def update_status(
        self,
        session_id: str,
        new_status: str,
    ) -> Session:
        """Transition session status with validation."""
        session = await self.get_session(session_id)
        if session is None:
            msg = f"Session {session_id} not found"
            raise ValueError(msg)
        _validate_transition(session.status, new_status)
        await self._execute(
            "UPDATE sessions SET status = $1 WHERE id = $2",
            new_status,
            session_id,
        )
        return await self.get_session(session_id)  # type: ignore[return-value]

    async def update_name(self, session_id: str, new_name: str) -> Session:
        """Rename a session. Validates non-empty and returns the updated row."""
        cleaned = (new_name or "").strip()
        if not cleaned:
            msg = "Session name must not be blank"
            raise ValueError(msg)
        result = await self._execute(
            "UPDATE sessions SET name = $1 WHERE id = $2",
            cleaned,
            session_id,
        )
        if result == "UPDATE 0":
            msg = f"Session {session_id} not found"
            raise ValueError(msg)
        return await self.get_session(session_id)  # type: ignore[return-value]

    async def update_review_gate_pause_scope(
        self,
        session_id: str,
        new_scope: str,
    ) -> Session:
        """Update review_gate_pause_scope. Returns the updated session."""
        if new_scope not in ("session", "participant"):
            msg = f"Invalid pause scope: {new_scope}"
            raise ValueError(msg)
        result = await self._execute(
            "UPDATE sessions SET review_gate_pause_scope = $1 WHERE id = $2",
            new_scope,
            session_id,
        )
        if result == "UPDATE 0":
            msg = f"Session {session_id} not found"
            raise ValueError(msg)
        return await self.get_session(session_id)  # type: ignore[return-value]

    async def delete_session(self, session_id: str) -> None:
        """Atomically remove all session data except audit log.

        Idempotent: a second call on an already-deleted session is a no-op.
        This prevents a NotNullViolationError when _log_deletion tries to read
        facilitator_id from a session row that no longer exists.
        """
        if await self.get_session(session_id) is None:
            return
        async with self._pool.acquire() as conn, conn.transaction():
            await _log_deletion(conn, session_id)
            await _delete_session_data(conn, session_id)

    async def update_length_cap(
        self,
        session_id: str,
        *,
        kind: str,
        seconds: int | None,
        turns: int | None,
    ) -> Session:
        """Spec 025 FR-003: commit a cap update to `sessions.length_cap_*`.

        Caller is responsible for cross-column consistency (kind=time
        requires seconds, etc.) and disambiguation per FR-026 — this
        helper is a pure UPDATE.
        """
        result = await self._execute(
            "UPDATE sessions SET length_cap_kind = $1, length_cap_seconds = $2, "
            "length_cap_turns = $3 WHERE id = $4",
            kind,
            seconds,
            turns,
            session_id,
        )
        if result == "UPDATE 0":
            msg = f"Session {session_id} not found"
            raise ValueError(msg)
        return await self.get_session(session_id)  # type: ignore[return-value]

    async def mark_conclude_phase_started(self, session_id: str) -> None:
        """Set `sessions.conclude_phase_started_at = now()` for spec 025 FR-007.

        Idempotent: a second call on a session already in conclude phase
        is a no-op (the column UPDATE just rewrites the same timestamp;
        callers should gate on `is_in_conclude_phase` first).
        """
        await self._execute(
            "UPDATE sessions SET conclude_phase_started_at = NOW() WHERE id = $1",
            session_id,
        )

    async def clear_conclude_phase(self, session_id: str) -> None:
        """Null `conclude_phase_started_at` for spec 025 US3 (`conclude_phase_exited`).

        Used by FR-013 cap-extension that returns the loop to running phase.
        Defined here for repo-test cohesion; US3 wires the call site.
        """
        await self._execute(
            "UPDATE sessions SET conclude_phase_started_at = NULL WHERE id = $1",
            session_id,
        )

    async def get_density_baseline(self, session_id: str) -> list[float]:
        """Read the rolling density baseline window (spec 004 §FR-020)."""
        record = await self._fetch_one(
            "SELECT density_baseline_window FROM sessions WHERE id = $1",
            session_id,
        )
        if record is None:
            return []
        raw = record["density_baseline_window"] or []
        return [float(v) for v in raw]

    async def replace_density_baseline(
        self,
        session_id: str,
        baseline_window: list[float],
    ) -> None:
        """Overwrite the rolling density baseline window for a session.

        Sessions table is mutable (status updates, name updates exist),
        so this UPDATE is consistent with existing patterns. Lives here
        rather than on LogRepository which is append-only by invariant.
        """
        await self._execute(
            "UPDATE sessions SET density_baseline_window = $1 WHERE id = $2",
            baseline_window,
            session_id,
        )


def _generate_ids() -> dict[str, str]:
    """Generate unique IDs for session creation."""
    return {
        "session": uuid.uuid4().hex[:12],
        "facilitator": uuid.uuid4().hex[:12],
    }


async def _fetch_created(
    conn: asyncpg.Connection,
    ids: dict[str, str],
    branch_id: str = "main",
) -> tuple[Session, Participant, Branch]:
    """Fetch the newly created session, facilitator, and branch."""
    session = await _fetch_session(conn, ids["session"])
    participant = await _fetch_participant(conn, ids["facilitator"])
    branch = await _fetch_branch(conn, branch_id)
    return session, participant, branch


async def _insert_session(
    conn: asyncpg.Connection,
    session_id: str,
    name: str,
    review_gate_pause_scope: str = "session",
) -> None:
    """Insert a new session record with defaults."""
    await conn.execute(
        "INSERT INTO sessions (id, name, review_gate_pause_scope) VALUES ($1, $2, $3)",
        session_id,
        name,
        review_gate_pause_scope,
    )


async def _insert_facilitator(
    conn: asyncpg.Connection,
    *,
    participant_id: str,
    session_id: str,
    display_name: str,
    provider: str,
    model: str,
    model_tier: str,
    model_family: str,
    context_window: int,
    api_endpoint: str | None = None,
) -> None:
    """Insert the facilitator participant record."""
    await conn.execute(
        """INSERT INTO participants
           (id, session_id, display_name, role, provider, model,
            model_tier, model_family, context_window, api_endpoint)
           VALUES ($1, $2, $3, 'facilitator', $4, $5, $6, $7, $8, $9)""",
        participant_id,
        session_id,
        display_name,
        provider,
        model,
        model_tier,
        model_family,
        context_window,
        api_endpoint,
    )


async def _link_facilitator(
    conn: asyncpg.Connection,
    session_id: str,
    facilitator_id: str,
) -> None:
    """Set the facilitator_id FK on the session."""
    await conn.execute(
        "UPDATE sessions SET facilitator_id = $1 WHERE id = $2",
        facilitator_id,
        session_id,
    )


async def _insert_main_branch(
    conn: asyncpg.Connection,
    branch_id: str,
    session_id: str,
    created_by: str,
) -> None:
    """Insert the required 'main' branch for the session."""
    await conn.execute(
        """INSERT INTO branches (id, session_id, name, created_by)
           VALUES ($1, $2, 'main', $3)""",
        branch_id,
        session_id,
        created_by,
    )


async def _fetch_session(
    conn: asyncpg.Connection,
    session_id: str,
) -> Session:
    """Fetch and return a Session from the database."""
    record = await conn.fetchrow(
        "SELECT * FROM sessions WHERE id = $1",
        session_id,
    )
    return Session.from_record(record)


async def _fetch_participant(
    conn: asyncpg.Connection,
    participant_id: str,
) -> Participant:
    """Fetch and return a Participant from the database."""
    record = await conn.fetchrow(
        "SELECT * FROM participants WHERE id = $1",
        participant_id,
    )
    return Participant.from_record(record)


async def _fetch_branch(
    conn: asyncpg.Connection,
    branch_id: str,
) -> Branch:
    """Fetch and return a Branch from the database."""
    record = await conn.fetchrow(
        "SELECT * FROM branches WHERE id = $1",
        branch_id,
    )
    return Branch.from_record(record)


# --- Lifecycle helpers ---

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "active": {"paused", "archived", "deleted"},
    "paused": {"active", "archived", "deleted"},
    "archived": {"deleted"},
}


def _validate_transition(current: str, target: str) -> None:
    """Raise InvalidTransitionError if the transition is illegal."""
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        msg = f"Cannot transition from '{current}' to '{target}'"
        raise InvalidTransitionError(msg)


async def _log_deletion(
    conn: asyncpg.Connection,
    session_id: str,
) -> None:
    """Record deletion in admin_audit_log before removing data."""
    facilitator_id = await conn.fetchval(
        "SELECT facilitator_id FROM sessions WHERE id = $1",
        session_id,
    )
    await conn.execute(
        """INSERT INTO admin_audit_log
           (session_id, facilitator_id, action, target_id)
           VALUES ($1, $2, 'delete_session', $1)""",
        session_id,
        facilitator_id,
    )


async def _delete_session_data(
    conn: asyncpg.Connection,
    session_id: str,
) -> None:
    """Remove all session data except admin_audit_log."""
    # Delete votes via proposals (votes has no session_id)
    await conn.execute(
        "DELETE FROM votes WHERE proposal_id IN (SELECT id FROM proposals WHERE session_id = $1)",
        session_id,
    )
    # Delete usage_log via participants (no session_id column)
    await conn.execute(
        "DELETE FROM usage_log WHERE participant_id IN"
        " (SELECT id FROM participants WHERE session_id = $1)",
        session_id,
    )
    # Delete tables with session_id column
    for table in _SESSION_TABLES:
        await conn.execute(
            f"DELETE FROM {table} WHERE session_id = $1",  # noqa: S608
            session_id,
        )
    await _delete_participants_and_session(conn, session_id)


_SESSION_TABLES = [
    "proposals",
    "invites",
    "review_gate_drafts",
    "interrupt_queue",
    "convergence_log",
    "routing_log",
    "messages",
    "branches",
]


async def _delete_participants_and_session(
    conn: asyncpg.Connection,
    session_id: str,
) -> None:
    """Remove participants and the session record itself.

    The admin_audit_log rows are preserved per 001 FR-019 + US5 §4. Migration
    007 dropped the FK constraints from admin_audit_log.session_id and
    admin_audit_log.facilitator_id so the rows survive as denormalized
    snapshots — including the `delete_session` action just written by
    `_log_deletion`.
    """
    await conn.execute(
        "UPDATE sessions SET facilitator_id = NULL WHERE id = $1",
        session_id,
    )
    await conn.execute(
        "DELETE FROM participants WHERE session_id = $1",
        session_id,
    )
    await conn.execute(
        "DELETE FROM sessions WHERE id = $1",
        session_id,
    )
