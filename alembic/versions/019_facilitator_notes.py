# SPDX-License-Identifier: AGPL-3.0-or-later

"""019: facilitator_notes table.

Backs spec 024 (facilitator scratch window).

  - `facilitator_notes` table — operator-private workspace state per
    spec 024 FR-001. Notes are NEVER assembled into AI context
    (architectural test `tests/test_024_architectural.py` enforces).
    Columns: TEXT id, session_id FK CASCADE, nullable account_id FK
    SET NULL (degrades to session-scoped on account deletion per
    clarify Q9), actor_participant_id FK CASCADE, content TEXT,
    version INTEGER for OCC, soft-delete deleted_at, promote markers
    (promoted_at + promoted_message_turn integer pointer; messages PK
    is composite so no FK). Three partial indexes filter deleted_at
    IS NULL for the hot-path query.

Revision ID: 019
Revises: 018
Create Date: 2026-05-12
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


_TABLE_SQL = """
    CREATE TABLE facilitator_notes (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL
            REFERENCES sessions(id) ON DELETE CASCADE,
        account_id UUID
            REFERENCES accounts(id) ON DELETE SET NULL,
        actor_participant_id TEXT NOT NULL
            REFERENCES participants(id) ON DELETE CASCADE,
        content TEXT NOT NULL CHECK (char_length(content) >= 1),
        version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at TIMESTAMPTZ,
        promoted_at TIMESTAMPTZ,
        promoted_message_turn INTEGER
    )
"""

_INDEX_SESSION_SQL = (
    "CREATE INDEX facilitator_notes_session_idx"
    " ON facilitator_notes (session_id) WHERE deleted_at IS NULL"
)
_INDEX_ACCOUNT_SQL = (
    "CREATE INDEX facilitator_notes_account_idx"
    " ON facilitator_notes (account_id)"
    " WHERE account_id IS NOT NULL AND deleted_at IS NULL"
)
_INDEX_SESSION_ACCOUNT_SQL = (
    "CREATE INDEX facilitator_notes_session_account_idx"
    " ON facilitator_notes (session_id, account_id) WHERE deleted_at IS NULL"
)


def upgrade() -> None:
    op.execute(_TABLE_SQL)
    op.execute(_INDEX_SESSION_SQL)
    op.execute(_INDEX_ACCOUNT_SQL)
    op.execute(_INDEX_SESSION_ACCOUNT_SQL)


def downgrade() -> None:
    """Forward-only migration per spec 001 FR-017."""
    pass
