# SPDX-License-Identifier: AGPL-3.0-or-later

"""003: Increase default turn timeout to 180s for Ollama cold starts.

Revision ID: 003
Revises: 002
Create Date: 2026-04-13
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Bump turn_timeout_seconds default from 60 to 180."""
    op.execute("ALTER TABLE participants" " ALTER COLUMN turn_timeout_seconds SET DEFAULT 180")


def downgrade() -> None:
    """Revert turn_timeout_seconds default to 60."""
    op.execute("ALTER TABLE participants" " ALTER COLUMN turn_timeout_seconds SET DEFAULT 60")
