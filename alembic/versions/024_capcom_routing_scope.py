# SPDX-License-Identifier: AGPL-3.0-or-later

"""024: CAPCOM-like routing scope (spec 028).

Adds visibility partitioning across the participant set:
  - messages.kind         TEXT NOT NULL DEFAULT 'utterance' CHECK (...)
  - messages.visibility   TEXT NOT NULL DEFAULT 'public' CHECK (...)
  - sessions.capcom_participant_id TEXT REFERENCES participants(id)
  - ux_participants_session_capcom UNIQUE partial index
  - idx_messages_visibility covering index

No row migration logic; every existing row inherits the column DEFAULT.

The two-tier summarizer storage shape (spec 028 §FR-018 / research.md §5)
defers to Phase 7's own migration after design adjustment to operate
against `messages` (spec 005 stores summaries inline as messages with
speaker_type='summary'; `checkpoint_summaries` table does not exist).

Revision ID: 024
Down revision: 023
"""

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages ADD COLUMN kind TEXT NOT NULL DEFAULT 'utterance' "
        "CHECK (kind IN ('utterance', 'capcom_relay', 'capcom_query'))"
    )
    op.execute(
        "ALTER TABLE messages ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public' "
        "CHECK (visibility IN ('public', 'capcom_only'))"
    )
    op.execute(
        "ALTER TABLE sessions ADD COLUMN capcom_participant_id TEXT " "REFERENCES participants(id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_participants_session_capcom "
        "ON participants(session_id) WHERE routing_preference = 'capcom'"
    )
    op.execute(
        "CREATE INDEX idx_messages_visibility "
        "ON messages(session_id, visibility, turn_number DESC)"
    )


def downgrade() -> None:
    """Forward-only migration per spec 001 §FR-017."""
    pass
