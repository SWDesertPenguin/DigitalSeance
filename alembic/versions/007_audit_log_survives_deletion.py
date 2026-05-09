# SPDX-License-Identifier: AGPL-3.0-or-later

"""007: Drop FK constraints from admin_audit_log so entries survive session deletion (CHK010).

Spec 001 FR-019 mandates that admin audit log entries be retained indefinitely
by default, and US5 §4 says session deletion atomically removes all data
"except the admin audit log entry recording the deletion." Pre-fix, the
session_id and facilitator_id columns on admin_audit_log carried NOT NULL
foreign keys to sessions / participants, so deleting either parent forced the
session_repo._delete_participants_and_session helper to delete the audit log
rows first — directly violating FR-019 + US5 §4.

The audit log is a denormalized append-only record by design (see CHK014 +
the spec-quality audit on 001). Dropping the FK constraints lets the audit
rows outlive their referenced session and participants. The columns stay
NOT NULL so we still capture which session/facilitator the action belonged
to, but they become plain TEXT identifiers rather than enforced references.

Revision ID: 007
Revises: 006
Create Date: 2026-04-29
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop FK constraints from admin_audit_log; columns remain NOT NULL TEXT."""
    op.execute(
        "ALTER TABLE admin_audit_log " "DROP CONSTRAINT IF EXISTS admin_audit_log_session_id_fkey"
    )
    op.execute(
        "ALTER TABLE admin_audit_log "
        "DROP CONSTRAINT IF EXISTS admin_audit_log_facilitator_id_fkey"
    )


def downgrade() -> None:
    """Restore FK constraints (only safe when no orphan audit rows exist)."""
    op.execute(
        "ALTER TABLE admin_audit_log "
        "ADD CONSTRAINT admin_audit_log_session_id_fkey "
        "FOREIGN KEY (session_id) REFERENCES sessions(id)"
    )
    op.execute(
        "ALTER TABLE admin_audit_log "
        "ADD CONSTRAINT admin_audit_log_facilitator_id_fkey "
        "FOREIGN KEY (facilitator_id) REFERENCES participants(id)"
    )
