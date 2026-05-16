# SPDX-License-Identifier: AGPL-3.0-or-later

"""025: Make auth_token_lookup mandatory when auth_token_hash is set.

Revision ID: 025
Revises: 024
Create Date: 2026-05-15

Audit C-02 finalization. Migration 009 added the HMAC-keyed lookup
column and an indexed-first probe path in ``_find_by_token``, but the
column stayed unconditionally nullable and the auth service retained
a legacy O(N) bcrypt-scan fallback for grandfathered rows whose lookup
was NULL. As long as the fallback existed any attacker who could
produce a single hash-bearing row with NULL lookup (deliberately or
via incomplete write paths) could re-open the O(N) DoS vector.

This migration closes that door:

  1. Pre-sweep check. Count rows where ``auth_token_hash IS NOT NULL
     AND auth_token_lookup IS NULL``. If any exist, RAISE EXCEPTION
     with a pointer to the pre-sweep runbook so the operator force-
     rotates or NULLs the dangling hash before re-running.

  2. CHECK constraint. ``auth_token_hash IS NULL OR auth_token_lookup
     IS NOT NULL`` -- the column is still nullable (revoked / departed
     participants legitimately have both NULL) but the hash-implies-
     lookup invariant is now enforced at the storage layer.

The existing partial index from migration 009 remains correct:
``WHERE auth_token_lookup IS NOT NULL`` still matches every authable
row exactly once.

Operator runbook: docs/runbooks/auth-token-lookup-finalization.md
Key-rotation runbook: docs/runbooks/auth-token-lookup-key-rotation.md
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

_PRE_SWEEP_GUARD = """
DO $$
DECLARE
    stranded_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO stranded_count
    FROM participants
    WHERE auth_token_hash IS NOT NULL
      AND auth_token_lookup IS NULL;
    IF stranded_count > 0 THEN
        RAISE EXCEPTION
            'alembic 025: % participants have auth_token_hash '
            'without auth_token_lookup. Run the pre-sweep '
            'runbook before upgrading: '
            'docs/runbooks/auth-token-lookup-finalization.md',
            stranded_count;
    END IF;
END
$$;
"""

_ADD_CHECK_CONSTRAINT = (
    "ALTER TABLE participants "
    "ADD CONSTRAINT ck_participants_lookup_when_hash "
    "CHECK (auth_token_hash IS NULL OR auth_token_lookup IS NOT NULL)"
)


def upgrade() -> None:
    """Refuse to run if grandfathered rows exist; then add CHECK."""
    op.execute(_PRE_SWEEP_GUARD)
    op.execute(_ADD_CHECK_CONSTRAINT)


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
