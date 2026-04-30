"""008: Per-stage instrumentation columns + facilitator-override audit fields.

Adds the columns that back V14 performance budgets (Constitution §12) and
§4.9 secure-by-design facilitator-override audit (FR-006). All additive,
all nullable. Forward-only per Constitution §6 + 001 §FR-017.

Per `routing_log` (003 §FR-030 codified the contract; instrumentation
implementation is feature 012 US6):
- route_ms, assemble_ms, dispatch_ms, persist_ms — per-stage durations
- advisory_lock_wait_ms — 003 §FR-032 advisory-lock contention metric

Per `security_events` (007 §FR-020 codified layer durations; §4.9
implementation under feature 012 US4 adds the override audit fields):
- layer_duration_ms — per-layer pipeline duration (007 §FR-020)
- override_reason — facilitator override justification, populated only when
  event_type='facilitator_override' (recorded if approach (b) is chosen
  in the §4.9 architectural review session, per spec 012 FR-006)
- override_actor_id — TEXT FK-style reference to participants.id of the
  facilitator who issued the override (no FK constraint to allow audit
  rows to outlive participant deletion, mirroring 001 admin_audit_log
  pattern from migration 007)

Revision ID: 008
Revises: 007
Create Date: 2026-04-30
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add per-stage timing + override audit columns."""
    _add_routing_log_timing_columns()
    _add_security_events_columns()


def _add_routing_log_timing_columns() -> None:
    op.execute("ALTER TABLE routing_log ADD COLUMN route_ms INTEGER")
    op.execute("ALTER TABLE routing_log ADD COLUMN assemble_ms INTEGER")
    op.execute("ALTER TABLE routing_log ADD COLUMN dispatch_ms INTEGER")
    op.execute("ALTER TABLE routing_log ADD COLUMN persist_ms INTEGER")
    op.execute("ALTER TABLE routing_log ADD COLUMN advisory_lock_wait_ms INTEGER")


def _add_security_events_columns() -> None:
    op.execute("ALTER TABLE security_events ADD COLUMN layer_duration_ms INTEGER")
    op.execute("ALTER TABLE security_events ADD COLUMN override_reason TEXT")
    op.execute("ALTER TABLE security_events ADD COLUMN override_actor_id TEXT")


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
