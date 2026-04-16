"""004: Fix convergence_log PK to include session_id.

Without session_id in the primary key, a second session on the same
database crashes with UniqueViolationError on turn_number collision.

Revision ID: 004
Revises: 003
Create Date: 2026-04-15
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace turn_number-only PK with (turn_number, session_id)."""
    op.execute("ALTER TABLE convergence_log" " DROP CONSTRAINT convergence_log_pkey")
    op.execute("ALTER TABLE convergence_log" " ADD PRIMARY KEY (turn_number, session_id)")


def downgrade() -> None:
    """Revert to turn_number-only PK."""
    op.execute("ALTER TABLE convergence_log" " DROP CONSTRAINT convergence_log_pkey")
    op.execute("ALTER TABLE convergence_log" " ADD PRIMARY KEY (turn_number)")
