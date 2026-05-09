# SPDX-License-Identifier: AGPL-3.0-or-later

"""013: Add (session_id, timestamp DESC) index to admin_audit_log.

Spec 029 §FR-001 / FR-005 — the human-readable audit log viewer's read
path queries the table by ``session_id`` with ``ORDER BY timestamp DESC
LIMIT N OFFSET M`` and a parallel ``COUNT(*)`` over the same WHERE.
Without a matching composite index, large audit logs degrade to a
sequential scan + sort, missing the V14 P95 ≤ 500ms latency contract
(plan.md Performance Goals).

The original ``admin_audit_log`` create-table migration (alembic 001)
shipped no per-table indexes. This migration adds
``idx_admin_audit_log_session_timestamp`` to cover the FR-001 endpoint
query plan. ``IF NOT EXISTS`` guards a re-run on environments that may
have hand-applied the index out-of-band (forward-only operational
hygiene per Constitution §6).

Revision ID: 013
Revises: 012
Create Date: 2026-05-09
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add covering index for the spec 029 FR-001 endpoint query plan."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_audit_log_session_timestamp "
        "ON admin_audit_log (session_id, timestamp DESC)"
    )


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
