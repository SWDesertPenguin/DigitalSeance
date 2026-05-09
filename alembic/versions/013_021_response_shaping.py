# SPDX-License-Identifier: AGPL-3.0-or-later

"""013: AI response shaping — register tables + routing_log shaping columns.

Backs spec 021 (AI response shaping):

  - `session_register` table — one row per session holding the session-level
    register slider value (1-5). Created on first facilitator slider-set;
    subsequent sets UPDATE in place.
  - `participant_register_override` table — zero-or-one row per participant
    holding a per-participant override of the session slider. Created on
    first override-set; subsequent sets UPDATE in place; explicit clear is
    a DELETE. Cascades on participant or session delete (FR-015 / SC-007).
  - Five new `routing_log` columns capturing each shaping decision per
    FR-011 + V14: per-stage timings (`shaping_score_ms`,
    `shaping_retry_dispatch_ms`), the aggregate filler score
    (`filler_score`), the tightened-delta text used on a retry
    (`shaping_retry_delta_text`), and the disposition reason
    (`shaping_reason`). All five default NULL so existing rows and
    shaping-disabled dispatches are byte-equal to the pre-feature baseline
    (SC-002).

FK note: data-model.md lists `set_by_facilitator_id` as referencing
`facilitators(id)`. The actual schema has no `facilitators` table —
facilitator is a role on `participants`. The FK is therefore to
`participants(id)`, matching the existing `sessions.facilitator_id`
pattern (alembic 001).

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
    """Create register tables and extend routing_log."""
    _create_session_register()
    _create_participant_register_override()
    _add_routing_log_shaping_columns()


def _create_session_register() -> None:
    op.execute("""
        CREATE TABLE session_register (
            session_id TEXT PRIMARY KEY
                REFERENCES sessions(id) ON DELETE CASCADE,
            slider_value INTEGER NOT NULL
                CHECK (slider_value BETWEEN 1 AND 5),
            set_by_facilitator_id TEXT NOT NULL
                REFERENCES participants(id),
            last_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def _create_participant_register_override() -> None:
    op.execute("""
        CREATE TABLE participant_register_override (
            participant_id TEXT PRIMARY KEY
                REFERENCES participants(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL
                REFERENCES sessions(id) ON DELETE CASCADE,
            slider_value INTEGER NOT NULL
                CHECK (slider_value BETWEEN 1 AND 5),
            set_by_facilitator_id TEXT NOT NULL
                REFERENCES participants(id),
            last_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX participant_register_override_session_idx"
        " ON participant_register_override (session_id)"
    )


def _add_routing_log_shaping_columns() -> None:
    op.execute("ALTER TABLE routing_log ADD COLUMN shaping_score_ms INTEGER")
    op.execute("ALTER TABLE routing_log ADD COLUMN shaping_retry_dispatch_ms INTEGER")
    op.execute("ALTER TABLE routing_log ADD COLUMN filler_score NUMERIC(4,3)")
    op.execute("ALTER TABLE routing_log ADD COLUMN shaping_retry_delta_text TEXT")
    op.execute("ALTER TABLE routing_log ADD COLUMN shaping_reason TEXT")


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
