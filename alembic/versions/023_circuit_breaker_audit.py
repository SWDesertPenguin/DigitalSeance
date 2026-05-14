# SPDX-License-Identifier: AGPL-3.0-or-later

"""023: Circuit breaker audit tables.

Backs spec 015 (provider failure detection). Three append-only audit tables:
  - provider_circuit_open_log  -- tripped to open (FR-012, US3 AS1)
  - provider_circuit_probe_log -- each probe attempt (FR-012, US3 AS4)
  - provider_circuit_close_log -- closed (FR-012, US3 AS3)

No changes to existing tables.
down_revision = "021" (spec 030 Phase 4 pre-allocates 022; this spec uses 023
per data-model.md migration-chain note).
"""

from alembic import op

revision = "023"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE provider_circuit_open_log (
            id              BIGSERIAL PRIMARY KEY,
            session_id      TEXT NOT NULL,
            participant_id  TEXT NOT NULL,
            provider        TEXT NOT NULL,
            api_key_fingerprint TEXT NOT NULL,
            trigger_reason  TEXT NOT NULL,
            failure_count   INTEGER NOT NULL,
            window_seconds  INTEGER NOT NULL,
            opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_circuit_open_session"
        " ON provider_circuit_open_log (session_id, opened_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE provider_circuit_probe_log (
            id              BIGSERIAL PRIMARY KEY,
            session_id      TEXT NOT NULL,
            participant_id  TEXT NOT NULL,
            provider        TEXT NOT NULL,
            api_key_fingerprint TEXT NOT NULL,
            probe_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            probe_outcome   TEXT NOT NULL,
            probe_latency_ms INTEGER NOT NULL,
            schedule_position INTEGER NOT NULL,
            schedule_exhausted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_circuit_probe_session"
        " ON provider_circuit_probe_log (session_id, probe_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE provider_circuit_close_log (
            id              BIGSERIAL PRIMARY KEY,
            session_id      TEXT NOT NULL,
            participant_id  TEXT NOT NULL,
            provider        TEXT NOT NULL,
            api_key_fingerprint TEXT NOT NULL,
            closed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            total_open_seconds INTEGER NOT NULL,
            probes_attempted INTEGER NOT NULL,
            probes_succeeded INTEGER NOT NULL,
            trigger_reason  TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_circuit_close_session"
        " ON provider_circuit_close_log (session_id, closed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS provider_circuit_close_log")
    op.execute("DROP TABLE IF EXISTS provider_circuit_probe_log")
    op.execute("DROP TABLE IF EXISTS provider_circuit_open_log")
