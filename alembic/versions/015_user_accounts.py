# SPDX-License-Identifier: AGPL-3.0-or-later

"""015: User accounts — accounts + account_participants tables.

Backs spec 023 (user accounts with persistent session history). Adds two
new tables and zero changes to existing tables. The `participants` row
remains the per-session security primitive untouched; the account is an
ownership pointer ABOVE the token (FR-016).

  - `accounts` table — one row per registered user. Columns per
    data-model.md: UUID id, email (lower-cased application-side; partial
    unique index covering only pending_verification + active rows so a
    deleted-account row coexists with a fresh registration after the
    grace period), password_hash (argon2id encoded; empty-string sentinel
    on deletion), status (CHECK-constrained text — pending_verification /
    active / deleted), and the four timestamp columns plus
    email_grace_release_at populated at deletion time from
    SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS.
  - `account_participants` table — zero-or-more join rows binding an
    account to per-session participant records. UUID id, account_id FK
    to accounts(id) ON DELETE RESTRICT (FR-012's preserve-row-on-delete
    contract), participant_id FK to participants(id) ON DELETE CASCADE +
    UNIQUE (FR-002's at-most-one-account-per-participant invariant), and
    a btree index on account_id for the /me/sessions lookup
    (research.md §9).

Pre-allocated revision slot: revision = '015', down_revision = '014' per
the dispatcher's lane-A brief. Slot 014 is taken by spec 029's
audit-log-session-timestamp index. Forward-only per Constitution §6 +
001 §FR-017 (downgrade is a no-op).

Revision ID: 015
Revises: 014
Create Date: 2026-05-09
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create accounts + account_participants tables."""
    _create_accounts()
    _create_account_participants()


def _create_accounts() -> None:
    op.execute("""
        CREATE TABLE accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_verification'
                CHECK (status IN ('pending_verification', 'active', 'deleted')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ,
            email_grace_release_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX accounts_email_active_uidx"
        " ON accounts (email)"
        " WHERE status IN ('pending_verification', 'active')"
    )


def _create_account_participants() -> None:
    op.execute("""
        CREATE TABLE account_participants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL
                REFERENCES accounts(id) ON DELETE RESTRICT,
            participant_id TEXT NOT NULL UNIQUE
                REFERENCES participants(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX account_participants_account_idx" " ON account_participants (account_id)"
    )


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
