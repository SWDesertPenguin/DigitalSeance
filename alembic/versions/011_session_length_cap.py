# SPDX-License-Identifier: AGPL-3.0-or-later

"""011: Session length cap — five new sessions columns for spec 025.

Backs spec 025 FR-001 (cap shape) and FR-002 (active-time accumulator).
All five columns are nullable; existing sessions inherit `length_cap_kind
= 'none'` (and NULL for the rest), which preserves the pre-feature loop
behavior unchanged (SC-001).

sessions:
  - `length_cap_kind` TEXT NOT NULL DEFAULT 'none' with CHECK constraint
    in ('none', 'time', 'turns', 'both').
  - `length_cap_seconds` BIGINT, range CHECK [60, 2_592_000] when set
    (1 minute to 30 days; FR-020).
  - `length_cap_turns` INTEGER, range CHECK [1, 10_000] when set
    (FR-020).
  - `conclude_phase_started_at` TIMESTAMPTZ, populated on running →
    conclude transitions.
  - `active_seconds_accumulator` BIGINT >= 0, durable wall-clock counter
    advancing only during running + conclude phases (FR-002, research §1).

Cross-column validity (kind='time' requires seconds, etc.) is enforced
application-side per data-model.md "Schema additions" — Postgres CHECK
constraints across nullable columns are awkward to express precisely
and the application layer already validates on cap-set.

Revision ID: 011
Revises: 010
Create Date: 2026-05-07
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the five session-length-cap columns to sessions."""
    op.execute(
        "ALTER TABLE sessions ADD COLUMN length_cap_kind TEXT NOT NULL DEFAULT 'none' "
        "CHECK (length_cap_kind IN ('none', 'time', 'turns', 'both'))"
    )
    op.execute(
        "ALTER TABLE sessions ADD COLUMN length_cap_seconds BIGINT "
        "CHECK (length_cap_seconds IS NULL OR length_cap_seconds BETWEEN 60 AND 2592000)"
    )
    op.execute(
        "ALTER TABLE sessions ADD COLUMN length_cap_turns INTEGER "
        "CHECK (length_cap_turns IS NULL OR length_cap_turns BETWEEN 1 AND 10000)"
    )
    op.execute("ALTER TABLE sessions ADD COLUMN conclude_phase_started_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE sessions ADD COLUMN active_seconds_accumulator BIGINT "
        "CHECK (active_seconds_accumulator IS NULL OR active_seconds_accumulator >= 0)"
    )


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
