# SPDX-License-Identifier: AGPL-3.0-or-later

"""018: Compression log + sessions.compression_mode column.

Backs spec 026 (context compression and distillation, six-layer stack).
Adds one new table and one new column.

  - `compression_log` table — append-only per-dispatch telemetry per
    Session 2026-05-11 §2. One row per CompressorService.compress()
    invocation INCLUDING NoOp dispatches per FR-007 + SC-013. Columns:
    BIGSERIAL id, session_id, turn_id, participant_id, source_tokens,
    output_tokens, compressor_id (CHECK-constrained to the registered
    set), compressor_version, trust_tier (CHECK-constrained to
    system/facilitator/participant_supplied), layer, duration_ms (V14
    Layer 4 budget enforcement), created_at. Two indexes:
    (session_id, created_at DESC) for the primary cross-spec read pattern
    and (compressor_id, created_at DESC) for spec 016 metrics group-by.

  - `sessions.compression_mode` column — per-session compressor
    selection override per FR-026. NOT NULL DEFAULT 'auto'; CHECK
    constrained to the seven-value enum (auto, off, noop,
    llmlingua2_mbert, selective_context, provence, layer6). Existing
    rows get 'auto' via the DEFAULT.

Pre-allocated revision slot: revision = '018'. down_revision points
at '016' for now (current chain head on main as of 2026-05-11). When
spec 022's `017_detection_events.py` lands first via PR merge, this
file must be rebased to point down_revision='017'. Coordination per
`feedback_parallel_merge_sequence_collisions`. Forward-only per
Constitution §6 + 001 §FR-017 (downgrade is a no-op).

Revision ID: 018
Revises: 017
Create Date: 2026-05-11
"""

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


_COMPRESSOR_ID_CHECK = (
    "compressor_id IN ('noop', 'llmlingua2_mbert', 'selective_context', " "'provence', 'layer6')"
)
_TRUST_TIER_CHECK = "trust_tier IN ('system', 'facilitator', 'participant_supplied')"
_COMPRESSION_MODE_CHECK = (
    "compression_mode IN ('auto', 'off', 'noop', 'llmlingua2_mbert', "
    "'selective_context', 'provence', 'layer6')"
)


def _create_compression_log_table() -> None:
    op.create_table(
        "compression_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("turn_id", sa.Text, nullable=False),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column("source_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("compressor_id", sa.Text, nullable=False),
        sa.Column("compressor_version", sa.Text, nullable=False),
        sa.Column("trust_tier", sa.Text, nullable=False),
        sa.Column("layer", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Float, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("source_tokens >= 0", name="compression_log_source_tokens_nonneg"),
        sa.CheckConstraint("output_tokens >= 0", name="compression_log_output_tokens_nonneg"),
        sa.CheckConstraint("duration_ms >= 0", name="compression_log_duration_ms_nonneg"),
        sa.CheckConstraint(_TRUST_TIER_CHECK, name="compression_log_trust_tier_enum"),
        sa.CheckConstraint(_COMPRESSOR_ID_CHECK, name="compression_log_compressor_id_enum"),
    )


def _create_compression_log_indexes() -> None:
    op.create_index(
        "compression_log_session_created_idx",
        "compression_log",
        ["session_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "compression_log_compressor_created_idx",
        "compression_log",
        ["compressor_id", sa.text("created_at DESC")],
    )


def _add_compression_mode_column() -> None:
    op.add_column(
        "sessions",
        sa.Column("compression_mode", sa.Text, nullable=False, server_default="auto"),
    )
    op.create_check_constraint(
        "sessions_compression_mode_enum",
        "sessions",
        _COMPRESSION_MODE_CHECK,
    )


def upgrade() -> None:
    _create_compression_log_table()
    _create_compression_log_indexes()
    _add_compression_mode_column()


def downgrade() -> None:
    """Forward-only migration per spec 001 §FR-017."""
    pass
