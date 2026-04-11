"""Session and Branch repository — atomic creation, lifecycle queries."""

from __future__ import annotations

import uuid

import asyncpg

from src.models.participant import Participant
from src.models.session import Branch, Session
from src.repositories.base import BaseRepository


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
    ) -> tuple[Session, Participant, Branch]:
        """Atomically create session + facilitator + main branch."""
        ids = _generate_ids()
        async with self._pool.acquire() as conn, conn.transaction():
            await _insert_session(conn, ids["session"], name)
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
            )
            await _link_facilitator(conn, ids["session"], ids["facilitator"])
            await _insert_main_branch(conn, "main", ids["session"], ids["facilitator"])
            return await _fetch_created(conn, ids)

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


def _generate_ids() -> dict[str, str]:
    """Generate unique IDs for session creation."""
    return {
        "session": uuid.uuid4().hex[:12],
        "facilitator": uuid.uuid4().hex[:12],
    }


async def _fetch_created(
    conn: asyncpg.Connection,
    ids: dict[str, str],
) -> tuple[Session, Participant, Branch]:
    """Fetch the newly created session, facilitator, and branch."""
    session = await _fetch_session(conn, ids["session"])
    participant = await _fetch_participant(conn, ids["facilitator"])
    branch = await _fetch_branch(conn, "main")
    return session, participant, branch


async def _insert_session(
    conn: asyncpg.Connection,
    session_id: str,
    name: str,
) -> None:
    """Insert a new session record with defaults."""
    await conn.execute(
        "INSERT INTO sessions (id, name) VALUES ($1, $2)",
        session_id,
        name,
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
) -> None:
    """Insert the facilitator participant record."""
    await conn.execute(
        """INSERT INTO participants
           (id, session_id, display_name, role, provider, model,
            model_tier, model_family, context_window)
           VALUES ($1, $2, $3, 'facilitator', $4, $5, $6, $7, $8)""",
        participant_id,
        session_id,
        display_name,
        provider,
        model,
        model_tier,
        model_family,
        context_window,
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
