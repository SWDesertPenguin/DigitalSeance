"""006: Add security_events table for pipeline observability (CHK008).

Revision ID: 006
Revises: 005
Create Date: 2026-04-29
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create security_events table for per-layer pipeline detection records."""
    op.execute(
        """
        CREATE TABLE security_events (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            speaker_id TEXT NOT NULL REFERENCES participants(id),
            turn_number INTEGER NOT NULL,
            layer TEXT NOT NULL,
            risk_score REAL,
            findings TEXT NOT NULL,
            blocked BOOLEAN NOT NULL,
            timestamp TIMESTAMP DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX security_events_session_idx ON security_events(session_id, timestamp)")


def downgrade() -> None:
    """Drop security_events table."""
    op.execute("DROP INDEX IF EXISTS security_events_session_idx")
    op.execute("DROP TABLE IF EXISTS security_events")
