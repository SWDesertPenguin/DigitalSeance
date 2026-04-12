"""002: Add token expiry and IP binding columns.

Revision ID: 002
Revises: 001
Create Date: 2026-04-11
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add token_expires_at and bound_ip to participants."""
    op.execute("ALTER TABLE participants" " ADD COLUMN token_expires_at TIMESTAMP")
    op.execute("ALTER TABLE participants" " ADD COLUMN bound_ip TEXT")


def downgrade() -> None:
    """Remove token_expires_at and bound_ip from participants."""
    op.execute("ALTER TABLE participants DROP COLUMN IF EXISTS bound_ip")
    op.execute("ALTER TABLE participants" " DROP COLUMN IF EXISTS token_expires_at")
