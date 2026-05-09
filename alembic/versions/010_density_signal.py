# SPDX-License-Identifier: AGPL-3.0-or-later

"""010: Density signal — convergence_log tier + sessions baseline window.

Backs spec 004 §FR-020 (information-density anomaly logging). Two
shape changes, both forward-only and idempotent in the conventional
Alembic sense (operations are guarded by IF NOT EXISTS where Postgres
syntax allows).

convergence_log:
  - Add `tier TEXT NOT NULL DEFAULT 'convergence'` so density anomalies
    coexist with embedding-similarity rows on the same primary key
    surface (per the comm-design pipeline §6 step 8 placement).
  - Make `embedding` and `similarity_score` nullable — density anomaly
    rows do not carry an embedding (it would duplicate the convergence
    row's vector for the same turn) and have no similarity score.
  - Add `density_value` and `baseline_value` REAL columns; populated only
    on `tier='density_anomaly'` rows.
  - Replace PK (turn_number, session_id) with (turn_number, session_id,
    tier) so a single turn can carry both a convergence row and a
    density-anomaly row.

sessions:
  - Add `density_baseline_window REAL[] DEFAULT '{}'` carrying the
    rolling 20-turn density values for in-process anomaly comparison.

Revision ID: 010
Revises: 009
Create Date: 2026-05-02
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add density signal columns + extend convergence_log PK."""
    _extend_convergence_log()
    _add_session_baseline_column()


def _extend_convergence_log() -> None:
    op.execute("ALTER TABLE convergence_log ALTER COLUMN embedding DROP NOT NULL")
    op.execute("ALTER TABLE convergence_log ALTER COLUMN similarity_score DROP NOT NULL")
    op.execute("ALTER TABLE convergence_log ADD COLUMN tier TEXT NOT NULL DEFAULT 'convergence'")
    op.execute("ALTER TABLE convergence_log ADD COLUMN density_value REAL")
    op.execute("ALTER TABLE convergence_log ADD COLUMN baseline_value REAL")
    op.execute("ALTER TABLE convergence_log DROP CONSTRAINT convergence_log_pkey")
    op.execute("ALTER TABLE convergence_log ADD PRIMARY KEY (turn_number, session_id, tier)")


def _add_session_baseline_column() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN density_baseline_window REAL[] DEFAULT '{}'")


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
