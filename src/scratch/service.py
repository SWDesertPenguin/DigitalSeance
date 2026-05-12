# SPDX-License-Identifier: AGPL-3.0-or-later

"""ScratchService — coordinates the facilitator-notes repo + audit log.

Each note CRUD method writes one audit-log row per spec 024 FR-020;
the row carries previous/new content snapshots that the ScrubFilter
(spec 007 FR-012) processes via the existing `log_admin_action`
envelope.

Account-vs-session scope detection looks up the participant's
account binding via the `account_participants` join table; an
unbound participant produces session-scoped notes (account_id NULL).
"""

from __future__ import annotations

import secrets

import asyncpg

from src.models.facilitator_note import FacilitatorNote
from src.repositories.log_repo import LogRepository
from src.scratch.repository import FacilitatorNotesRepository

_ACCOUNT_LOOKUP_SQL = (
    "SELECT account_id::text AS account_id FROM account_participants" " WHERE participant_id = $1"
)

# Per spec 024 FR-013 + contracts/scratch-endpoints.md §1: the review-gate
# section of the FR-002 payload reads admin_audit_log filtered by the
# review-gate action set. The query mirrors the spec 029 audit-log page
# shape (newest-first, bounded LIMIT) but is scoped by action.
_REVIEW_GATE_EVENTS_SQL = (
    "SELECT id, action, facilitator_id, target_id, previous_value, new_value, timestamp "
    "FROM admin_audit_log "
    "WHERE session_id = $1 "
    "AND action LIKE 'review_gate_%' "
    "ORDER BY timestamp DESC "
    "LIMIT 50"
)

_SUMMARY_PAGE_SIZE = 20


def _new_note_id() -> str:
    """Mint an opaque note id; URL-safe token bounded at 22 chars."""
    return "note_" + secrets.token_urlsafe(16)


def _truncate_preview(content: str, max_chars: int = 200) -> str:
    """Truncate audit-log content preview to bounded size."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars]


class ScratchService:
    """High-level scratch operations composing repo + audit log + scope."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        notes_repo: FacilitatorNotesRepository,
        log_repo: LogRepository,
    ) -> None:
        self._pool = pool
        self._notes = notes_repo
        self._log = log_repo

    async def resolve_account_id(self, participant_id: str) -> str | None:
        """Return the account_id bound to this participant or None."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_ACCOUNT_LOOKUP_SQL, participant_id)
        return row["account_id"] if row is not None else None

    async def create_note(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        content: str,
    ) -> FacilitatorNote:
        """Insert + audit a new note."""
        account_id = await self.resolve_account_id(facilitator_id)
        note = await self._notes.create_note(
            note_id=_new_note_id(),
            session_id=session_id,
            account_id=account_id,
            actor_participant_id=facilitator_id,
            content=content,
        )
        await self._log.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="facilitator_note_created",
            target_id=note.id,
            previous_value=None,
            new_value=_truncate_preview(content),
            broadcast_session_id=session_id,
        )
        return note

    async def update_note(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        note_id: str,
        expected_version: int,
        content: str,
    ) -> FacilitatorNote | None:
        """OCC update + audit. Returns None on stale version."""
        prior = await self._notes.find_by_id(note_id)
        if prior is None:
            return None
        updated = await self._notes.update_note(
            note_id=note_id,
            expected_version=expected_version,
            content=content,
        )
        if updated is None:
            return None
        await self._log.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="facilitator_note_updated",
            target_id=note_id,
            previous_value=_truncate_preview(prior.content),
            new_value=_truncate_preview(content),
            broadcast_session_id=session_id,
        )
        return updated

    async def delete_note(
        self,
        *,
        session_id: str,
        facilitator_id: str,
        note_id: str,
    ) -> bool:
        """Soft-delete + audit. Returns True on success."""
        prior = await self._notes.find_by_id(note_id)
        if prior is None:
            return False
        deleted = await self._notes.soft_delete_note(note_id)
        if not deleted:
            return False
        await self._log.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="facilitator_note_deleted",
            target_id=note_id,
            previous_value=_truncate_preview(prior.content),
            new_value=None,
            broadcast_session_id=session_id,
        )
        return True

    async def list_for_session(
        self,
        *,
        session_id: str,
        facilitator_id: str,
    ) -> tuple[list[FacilitatorNote], str | None]:
        """Return the scoped note list plus the resolved account_id."""
        account_id = await self.resolve_account_id(facilitator_id)
        notes = await self._notes.list_for_session(
            session_id=session_id,
            account_id=account_id,
        )
        return notes, account_id

    async def list_summaries(
        self,
        *,
        session_id: str,
        branch_id: str,
        page: int = 0,
        page_size: int = _SUMMARY_PAGE_SIZE,
    ) -> tuple[list, int]:
        """Read summary-checkpoint messages for the FR-011 / FR-012 panel.

        Returns ``(items, total)`` where ``items`` is a slice of the
        chronologically-ordered summary messages bounded by the page
        offset. The summary archive is per-session bounded so the
        total query is cheap.
        """
        from src.repositories.message_repo import MessageRepository

        msg_repo = MessageRepository(self._pool)
        summaries = await msg_repo.get_summaries(session_id, branch_id)
        total = len(summaries)
        start = max(0, page) * page_size
        end = start + page_size
        return summaries[start:end], total

    async def list_review_gate_events(
        self,
        *,
        session_id: str,
    ) -> list[dict]:
        """Read review-gate audit rows for the FR-013 panel.

        Bounded LIMIT 50 per the contract; newest-first. Returns raw
        rows for the router to project into the wire shape (the
        action-label registry lookup happens at projection time).
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_REVIEW_GATE_EVENTS_SQL, session_id)
        return [dict(r) for r in rows]
