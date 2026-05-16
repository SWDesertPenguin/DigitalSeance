# SPDX-License-Identifier: AGPL-3.0-or-later

"""026: Grant least-privilege per-table access to the three runtime roles.

Audit Critical-4 finalization. The bootstrap init script
`scripts/db-init/00-create-sacp-roles.sh` creates the four SACP roles
(`sacp_admin`, `sacp_app`, `sacp_cleanup`, `sacp_audit_reader`) on first
cluster init and wires per-future-table default privileges. This migration
issues per-table grants for the 25 tables that already exist at chain head
when 026 ships -- the default privileges from the init script only apply
to tables created AFTER the init script runs.

Grant matrix by category:

  MUTABLE_TABLES (full CRUD path):
    sacp_app          -> SELECT, INSERT, UPDATE, DELETE
    sacp_cleanup      -> SELECT, DELETE
    sacp_audit_reader -> SELECT

  APPEND_ONLY_TABLES (logs / audit):
    sacp_app          -> SELECT, INSERT     (no UPDATE / DELETE)
    sacp_cleanup      -> SELECT, DELETE     (retention sweeps only)
    sacp_audit_reader -> SELECT

  Cross-category exceptions:
    sacp_cleanup gets INSERT on admin_audit_log so retention sweeps can
    write their own "purged N rows" audit row; same for security_events
    so a purge that hits security_events itself can audit its action.

All sequences in the public schema are granted USAGE + SELECT to sacp_app
and sacp_cleanup so SERIAL primary keys keep working after the runtime
DSN swaps off the superuser.

Idempotent: GRANT is naturally additive in Postgres -- re-running this
migration after a successful upgrade is a no-op. The image-baked CMD's
`alembic upgrade head` therefore emits no DDL when head is already
current, which is the property that lets the runtime container's image
default keep its chained `alembic upgrade head &&` call even when the
DSN points at sacp_app (no DDL = no privilege escalation needed).

Forward-only per Constitution §6 + 001 §FR-017.

Revision ID: 026
Revises: 025
Create Date: 2026-05-15
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


MUTABLE_TABLES: tuple[str, ...] = (
    "sessions",
    "participants",
    "branches",
    "interrupt_queue",
    "review_gate_drafts",
    "invites",
    "proposals",
    "session_register",
    "participant_register_override",
    "accounts",
    "account_participants",
    "facilitator_notes",
    "oauth_clients",
    "oauth_token_families",
    "oauth_authorization_codes",
    "oauth_access_tokens",
    "oauth_refresh_tokens",
)

APPEND_ONLY_TABLES: tuple[str, ...] = (
    "messages",
    "routing_log",
    "usage_log",
    "convergence_log",
    "admin_audit_log",
    "votes",
    "security_events",
    "detection_events",
    "compression_log",
    "provider_circuit_open_log",
    "provider_circuit_probe_log",
    "provider_circuit_close_log",
)


def _grant_mutable(tbl: str) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO sacp_app")
    op.execute(f"GRANT SELECT, DELETE ON {tbl} TO sacp_cleanup")
    op.execute(f"GRANT SELECT ON {tbl} TO sacp_audit_reader")


def _grant_append_only(tbl: str) -> None:
    op.execute(f"GRANT SELECT, INSERT ON {tbl} TO sacp_app")
    op.execute(f"GRANT SELECT ON {tbl} TO sacp_audit_reader")
    op.execute(f"GRANT SELECT, DELETE ON {tbl} TO sacp_cleanup")


def upgrade() -> None:
    for tbl in MUTABLE_TABLES:
        _grant_mutable(tbl)
    for tbl in APPEND_ONLY_TABLES:
        _grant_append_only(tbl)
    op.execute("GRANT INSERT ON admin_audit_log TO sacp_cleanup")
    op.execute("GRANT INSERT ON security_events TO sacp_cleanup")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sacp_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sacp_cleanup")


def downgrade() -> None:
    """Forward-only per Constitution §6 + spec 001 §FR-017.

    Revoking the per-table grants would lock the running orchestrator out
    of every table the moment the downgrade runs -- worse failure mode
    than the forward-only stance. Operators who need to drop the grants
    do so manually with a one-off REVOKE script while the orchestrator
    is offline.
    """
    pass
