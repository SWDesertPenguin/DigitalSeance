# SPDX-License-Identifier: AGPL-3.0-or-later

"""012: Active-phase tracker for spec 025 pause-aware time cap.

Adds `active_phase_started_at` (TIMESTAMPTZ, nullable) to `sessions`.
This column marks the moment the current running or conclude phase
began so the orchestrator can compute:

    active_seconds_accumulator += (now() - active_phase_started_at)

on pause/stop, and set it fresh on start_loop / resume_session.

The `effective_active_seconds` helper (src/orchestrator/length_cap.py)
reads `active_phase_started_at` to compute live elapsed correctly,
replacing the `now() - created_at` fallback for sessions that have
been through at least one start/pause cycle.

Revision ID: 012
Revises: 011
Create Date: 2026-05-08
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add active_phase_started_at to sessions."""
    op.execute("ALTER TABLE sessions ADD COLUMN active_phase_started_at TIMESTAMPTZ")


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
