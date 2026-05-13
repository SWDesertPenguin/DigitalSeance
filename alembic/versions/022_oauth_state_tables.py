# SPDX-License-Identifier: AGPL-3.0-or-later

"""022: OAuth 2.1 state tables + participants migration column.

Backs spec 030 Phase 4 (OAuth 2.1 + PKCE authorization server).
Creates five new tables under the ``oauth_*`` prefix and adds one
column to the existing ``participants`` table.

New tables:

  - ``oauth_clients`` - per-MCP-client CIMD registrations
  - ``oauth_authorization_codes`` - short-lived PKCE-bound auth codes
  - ``oauth_access_tokens`` - per-JTI revocation pointers for JWT tokens
  - ``oauth_refresh_tokens`` - Fernet-encrypted opaque refresh tokens
  - ``oauth_token_families`` - family tracking for replay detection

New column on ``participants``:

  - ``mcp_oauth_migration_prompted_at`` - TIMESTAMPTZ NULL. Records the
    first time a static-bearer holder was prompted to migrate to OAuth.
    After ``SACP_OAUTH_STATIC_TOKEN_GRACE_DAYS`` from this timestamp,
    static tokens on the MCP endpoint are hard-rejected.

Pre-allocated revision slot: revision = '022', down_revision = '021'.
Chain: ... -> 019 -> 021 -> 022. Revision 020 was intentionally skipped
in an earlier migration batch. Forward-only per Constitution §6.

Revision ID: 022
Revises: 021
Create Date: 2026-05-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def _create_oauth_clients() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.Text, primary_key=True),
        sa.Column("cimd_url", sa.Text, nullable=False),
        sa.Column("cimd_content", postgresql.JSONB, nullable=False),
        sa.Column("redirect_uris", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("allowed_scopes", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("registration_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "registration_status IN ('pending', 'approved', 'revoked')",
            name="oauth_clients_status_check",
        ),
    )
    op.create_index("idx_oauth_clients_cimd_url", "oauth_clients", ["cimd_url"], unique=True)


def _create_oauth_token_families() -> None:
    op.create_table(
        "oauth_token_families",
        sa.Column("family_id", sa.Text, primary_key=True),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column(
            "client_id",
            sa.Text,
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("root_token_hash", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_oauth_token_families_participant", "oauth_token_families", ["participant_id"]
    )


def _create_oauth_authorization_codes() -> None:
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("code_hash", sa.Text, primary_key=True),
        sa.Column(
            "client_id",
            sa.Text,
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column("redirect_uri", sa.Text, nullable=False),
        sa.Column("code_challenge", sa.Text, nullable=False),
        sa.Column("code_challenge_method", sa.Text, nullable=False, server_default="S256"),
        sa.Column("scope", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "code_challenge_method = 'S256'",
            name="oauth_authorization_codes_method_check",
        ),
    )
    op.create_index(
        "idx_oauth_auth_codes_client_issued",
        "oauth_authorization_codes",
        ["client_id", "issued_at"],
    )


def _create_oauth_refresh_tokens() -> None:
    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("token_hash", sa.Text, primary_key=True),
        sa.Column("encrypted_token", sa.LargeBinary, nullable=False),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column(
            "client_id",
            sa.Text,
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "family_id",
            sa.Text,
            sa.ForeignKey("oauth_token_families.family_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_token_hash",
            sa.Text,
            sa.ForeignKey("oauth_refresh_tokens.token_hash"),
            nullable=True,
        ),
    )
    op.create_index("idx_oauth_refresh_tokens_family", "oauth_refresh_tokens", ["family_id"])
    op.create_index(
        "idx_oauth_refresh_tokens_parent", "oauth_refresh_tokens", ["parent_token_hash"]
    )


def _create_oauth_access_tokens() -> None:
    op.create_table(
        "oauth_access_tokens",
        sa.Column("jti", sa.Text, primary_key=True),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column(
            "client_id",
            sa.Text,
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "family_id",
            sa.Text,
            sa.ForeignKey("oauth_token_families.family_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("auth_time", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_oauth_access_tokens_participant", "oauth_access_tokens", ["participant_id"]
    )
    op.create_index("idx_oauth_access_tokens_family", "oauth_access_tokens", ["family_id"])


def _add_migration_prompted_at_column() -> None:
    op.add_column(
        "participants",
        sa.Column("mcp_oauth_migration_prompted_at", sa.DateTime(timezone=True), nullable=True),
    )


def upgrade() -> None:
    _create_oauth_clients()
    _create_oauth_token_families()
    _create_oauth_authorization_codes()
    _create_oauth_refresh_tokens()
    _create_oauth_access_tokens()
    _add_migration_prompted_at_column()


def downgrade() -> None:
    """Forward-only migration per spec 001 §FR-017."""
    pass
