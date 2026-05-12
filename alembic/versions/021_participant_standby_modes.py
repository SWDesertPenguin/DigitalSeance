# SPDX-License-Identifier: AGPL-3.0-or-later

"""021: Participant standby modes + V14 timing columns on routing_log.

Backs spec 027 (AI participant standby modes — wait_for_human + always).
Adds three columns to ``participants``, three columns to ``routing_log``,
extends the ``participants.status`` CHECK constraint to permit the new
``standby`` value, and creates a partial index for the standby skip-set.

  - ``participants.wait_mode`` — TEXT NOT NULL DEFAULT 'wait_for_human',
    CHECK constrained to ``wait_for_human`` / ``always``. Existing rows
    get ``wait_for_human`` via the DEFAULT clause.

  - ``participants.standby_cycle_count`` — INTEGER NOT NULL DEFAULT 0.
    Counts consecutive round-robin ticks the participant remained in
    ``status='standby'``. Resets to 0 on standby-exit. Backs FR-017
    pivot-trigger denominator.

  - ``participants.wait_mode_metadata`` — JSONB NOT NULL DEFAULT
    '{}'::jsonb. v1 keys: ``long_term_observer`` boolean (FR-020).

  - ``participants.status`` CHECK constraint extended to permit
    ``standby`` alongside existing ``active`` / ``pending`` / ``paused``
    / ``removed`` / ``circuit_open``.

  - ``routing_log.standby_eval_ms`` / ``pivot_inject_ms`` /
    ``standby_transition_ms`` — INTEGER NULL. V14 per-stage timing
    columns. Pre-existing rows stay NULL (they pre-date the feature).

  - Partial index ``idx_participants_session_standby`` on
    ``(session_id, status) WHERE status='standby'`` so the standby
    skip-set query stays O(1) regardless of session size.

Pre-allocated revision slot: revision = '021'. Lane A (spec 024) uses
``019_*``; lane B (spec 026 ongoing) may use ``020_*``. If a different
chain head lands first via PR merge, ``down_revision`` must be rebased
to the post-merge head before this migration ships. Coordination per
``feedback_parallel_merge_sequence_collisions``. Forward-only per
Constitution §6 + spec 001 §FR-017 (downgrade is a no-op).

Revision ID: 021
Revises: 018
Create Date: 2026-05-12
"""

import sqlalchemy as sa

from alembic import op

revision = "021"
down_revision = "019"
branch_labels = None
depends_on = None


_PARTICIPANT_STATUS_CHECK_NAME = "participants_status_check"
_PARTICIPANT_STATUS_VALUES = (
    "status IN ('active', 'pending', 'paused', 'removed', 'circuit_open', 'standby')"
)
_WAIT_MODE_CHECK = "wait_mode IN ('wait_for_human', 'always')"


def _add_wait_mode_column() -> None:
    op.add_column(
        "participants",
        sa.Column(
            "wait_mode",
            sa.Text,
            nullable=False,
            server_default="wait_for_human",
        ),
    )
    op.create_check_constraint(
        "participants_wait_mode_enum",
        "participants",
        _WAIT_MODE_CHECK,
    )


def _add_standby_cycle_count_column() -> None:
    op.add_column(
        "participants",
        sa.Column(
            "standby_cycle_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def _add_wait_mode_metadata_column() -> None:
    op.add_column(
        "participants",
        sa.Column(
            "wait_mode_metadata",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def _extend_status_check_constraint() -> None:
    # Drop the existing CHECK constraint (if any) and recreate to permit
    # 'standby'. The constraint name is the alembic-default per the
    # original 001 migration; if not found, the DROP is a no-op.
    op.execute(
        f"ALTER TABLE participants DROP CONSTRAINT IF EXISTS {_PARTICIPANT_STATUS_CHECK_NAME}",
    )
    op.create_check_constraint(
        _PARTICIPANT_STATUS_CHECK_NAME,
        "participants",
        _PARTICIPANT_STATUS_VALUES,
    )


def _add_routing_log_timing_columns() -> None:
    op.add_column(
        "routing_log",
        sa.Column("standby_eval_ms", sa.Integer, nullable=True),
    )
    op.add_column(
        "routing_log",
        sa.Column("pivot_inject_ms", sa.Integer, nullable=True),
    )
    op.add_column(
        "routing_log",
        sa.Column("standby_transition_ms", sa.Integer, nullable=True),
    )


def _create_standby_partial_index() -> None:
    op.execute(
        "CREATE INDEX idx_participants_session_standby "
        "ON participants (session_id, status) "
        "WHERE status = 'standby'",
    )


def upgrade() -> None:
    _add_wait_mode_column()
    _add_standby_cycle_count_column()
    _add_wait_mode_metadata_column()
    _extend_status_check_constraint()
    _add_routing_log_timing_columns()
    _create_standby_partial_index()


def downgrade() -> None:
    """Forward-only migration per spec 001 §FR-017."""
    pass
