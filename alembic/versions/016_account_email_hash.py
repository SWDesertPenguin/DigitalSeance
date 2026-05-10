# SPDX-License-Identifier: AGPL-3.0-or-later

"""016: Spec 023 grace-period lookup column — accounts.email_hash.

Backs the grace-period reservation (FR-013). 015's mark_account_deleted
zeroes the ``email`` column for PII hygiene, so the grace-window lookup
cannot match the deleted row by email. Adds an ``email_hash`` column
populated at create time with HMAC-SHA256(SACP_AUTH_LOOKUP_KEY, email)
that survives deletion; the grace check queries by hash.

Existing rows get an empty-string sentinel (no rows in prod yet — 015
just landed). New accounts compute the hash application-side.

Revision ID: 016
Revises: 015
Create Date: 2026-05-09
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE accounts ADD COLUMN email_hash TEXT NOT NULL DEFAULT ''")
    op.execute(
        "CREATE INDEX accounts_email_hash_grace_idx"
        " ON accounts (email_hash)"
        " WHERE status = 'deleted' AND email_grace_release_at IS NOT NULL"
    )


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
