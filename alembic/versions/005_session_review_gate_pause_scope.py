"""005: Add review_gate_pause_scope column to sessions.

Revision ID: 005
Revises: 004
Create Date: 2026-04-19
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add review_gate_pause_scope to sessions with CHECK constraint."""
    op.execute(
        "ALTER TABLE sessions" " ADD COLUMN review_gate_pause_scope TEXT NOT NULL DEFAULT 'session'"
    )
    op.execute(
        "ALTER TABLE sessions"
        " ADD CONSTRAINT sessions_review_gate_pause_scope_check"
        " CHECK (review_gate_pause_scope IN ('session', 'participant'))"
    )


def downgrade() -> None:
    """Remove review_gate_pause_scope from sessions."""
    op.execute(
        "ALTER TABLE sessions" " DROP CONSTRAINT IF EXISTS sessions_review_gate_pause_scope_check"
    )
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS review_gate_pause_scope")
