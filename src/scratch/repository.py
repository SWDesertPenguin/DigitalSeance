# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repository for `facilitator_notes` rows (spec 024 §FR-001..FR-005).

Operator-private workspace state. The FR-001 architectural test
(tests/test_024_architectural.py) enforces that this module is NOT
imported from any AI context-assembly path.

Public surface:
  - create_note: insert a new row with version 1.
  - update_note: OCC on version; returns None on stale write.
  - soft_delete_note: sets deleted_at on the row.
  - find_by_id: fetch one note (with scope filtering).
  - list_for_session: list non-deleted notes scoped by account.
  - mark_promoted: stamp promoted_at + promoted_message_turn.
"""

from __future__ import annotations

from typing import Any

from src.models.facilitator_note import FacilitatorNote
from src.repositories.base import BaseRepository

_INSERT_SQL = """
    INSERT INTO facilitator_notes (
        id, session_id, account_id, actor_participant_id, content
    ) VALUES ($1, $2, $3, $4, $5)
    RETURNING id, session_id, account_id, actor_participant_id, content,
              version, created_at, updated_at, deleted_at, promoted_at,
              promoted_message_turn
"""

_UPDATE_SQL = """
    UPDATE facilitator_notes
       SET content = $3, version = version + 1, updated_at = NOW()
     WHERE id = $1 AND version = $2 AND deleted_at IS NULL
    RETURNING id, session_id, account_id, actor_participant_id, content,
              version, created_at, updated_at, deleted_at, promoted_at,
              promoted_message_turn
"""

_SOFT_DELETE_SQL = """
    UPDATE facilitator_notes
       SET deleted_at = NOW(), updated_at = NOW()
     WHERE id = $1 AND deleted_at IS NULL
    RETURNING id
"""

_FIND_ONE_SQL = """
    SELECT id, session_id, account_id, actor_participant_id, content,
           version, created_at, updated_at, deleted_at, promoted_at,
           promoted_message_turn
      FROM facilitator_notes
     WHERE id = $1 AND deleted_at IS NULL
"""

_LIST_SESSION_NO_ACCOUNT_SQL = """
    SELECT id, session_id, account_id, actor_participant_id, content,
           version, created_at, updated_at, deleted_at, promoted_at,
           promoted_message_turn
      FROM facilitator_notes
     WHERE session_id = $1 AND account_id IS NULL AND deleted_at IS NULL
     ORDER BY created_at DESC
"""

_LIST_SESSION_WITH_ACCOUNT_SQL = """
    SELECT id, session_id, account_id, actor_participant_id, content,
           version, created_at, updated_at, deleted_at, promoted_at,
           promoted_message_turn
      FROM facilitator_notes
     WHERE session_id = $1 AND account_id = $2 AND deleted_at IS NULL
     ORDER BY created_at DESC
"""

_MARK_PROMOTED_SQL = """
    UPDATE facilitator_notes
       SET promoted_at = NOW(), promoted_message_turn = $2, updated_at = NOW()
     WHERE id = $1 AND deleted_at IS NULL
    RETURNING id, session_id, account_id, actor_participant_id, content,
              version, created_at, updated_at, deleted_at, promoted_at,
              promoted_message_turn
"""


def _row_to_note(row: Any) -> FacilitatorNote:
    return FacilitatorNote(
        id=row["id"],
        session_id=row["session_id"],
        account_id=str(row["account_id"]) if row["account_id"] is not None else None,
        actor_participant_id=row["actor_participant_id"],
        content=row["content"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        promoted_at=row["promoted_at"],
        promoted_message_turn=row["promoted_message_turn"],
    )


class FacilitatorNotesRepository(BaseRepository):
    """CRUD + OCC on the `facilitator_notes` table."""

    async def create_note(
        self,
        *,
        note_id: str,
        session_id: str,
        account_id: str | None,
        actor_participant_id: str,
        content: str,
    ) -> FacilitatorNote:
        """Insert a new note row at version=1."""
        row = await self._fetch_one(
            _INSERT_SQL,
            note_id,
            session_id,
            account_id,
            actor_participant_id,
            content,
        )
        if row is None:
            raise RuntimeError("facilitator_notes insert returned no row")
        return _row_to_note(row)

    async def update_note(
        self,
        *,
        note_id: str,
        expected_version: int,
        content: str,
    ) -> FacilitatorNote | None:
        """Update via OCC. Returns None when the version is stale or note deleted."""
        row = await self._fetch_one(_UPDATE_SQL, note_id, expected_version, content)
        return _row_to_note(row) if row is not None else None

    async def soft_delete_note(self, note_id: str) -> bool:
        """Soft-delete a note. Returns True when the row was deleted."""
        row = await self._fetch_one(_SOFT_DELETE_SQL, note_id)
        return row is not None

    async def find_by_id(self, note_id: str) -> FacilitatorNote | None:
        """Fetch one non-deleted note by id."""
        row = await self._fetch_one(_FIND_ONE_SQL, note_id)
        return _row_to_note(row) if row is not None else None

    async def list_for_session(
        self,
        *,
        session_id: str,
        account_id: str | None,
    ) -> list[FacilitatorNote]:
        """List non-deleted notes scoped by (session_id, account_id)."""
        if account_id is None:
            rows = await self._fetch_all(_LIST_SESSION_NO_ACCOUNT_SQL, session_id)
        else:
            rows = await self._fetch_all(_LIST_SESSION_WITH_ACCOUNT_SQL, session_id, account_id)
        return [_row_to_note(r) for r in rows]

    async def mark_promoted(
        self,
        *,
        note_id: str,
        message_turn: int,
    ) -> FacilitatorNote | None:
        """Stamp promote markers on the row. Returns the updated row or None."""
        row = await self._fetch_one(_MARK_PROMOTED_SQL, note_id, message_turn)
        return _row_to_note(row) if row is not None else None
