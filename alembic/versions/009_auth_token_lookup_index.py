# SPDX-License-Identifier: AGPL-3.0-or-later

"""009: Add HMAC-keyed auth_token_lookup column for indexed token resolution.

Revision ID: 009
Revises: 008
Create Date: 2026-05-01

Audit C-02. Pre-fix the auth path bcrypt-scanned every row in
participants where auth_token_hash IS NOT NULL on every authenticate()
call -- O(N) with bcrypt's slow-by-design constant per row, plus a
per-row timing channel.

Adds an HMAC(SACP_AUTH_LOOKUP_KEY, plaintext)-derived deterministic
column with an index. New tokens get the lookup populated at write
time (add_participant + rotate_token); revoke_token nulls it. The auth
service does an O(log N) lookup-column probe first, falls back to the
old scan only for grandfathered rows where the lookup is NULL (existing
sessions before this migration). Every rotation populates the lookup
column, so the fallback path drains naturally.
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add auth_token_lookup column + index."""
    op.execute("ALTER TABLE participants ADD COLUMN auth_token_lookup TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_participants_auth_token_lookup "
        "ON participants (auth_token_lookup) "
        "WHERE auth_token_lookup IS NOT NULL"
    )


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
