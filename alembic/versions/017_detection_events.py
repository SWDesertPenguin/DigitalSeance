# SPDX-License-Identifier: AGPL-3.0-or-later

"""017: detection_events table for spec 022 history surface.

Adds the dedicated persistence table the spec 022 history panel reads
from. Per the Session 2026-05-11 amendment, this table replaces the
read-side join over (routing_log, convergence_log, admin_audit_log)
because two of the five event classes (question, exit) were never
persisted and density-anomaly rows lack participant attribution.

Schema follows spec 007's no-FK pattern for log tables so detection
events survive session deletion for audit purposes (FR-008 append-only
invariant on log content; only the latest-state disposition column
is updatable).

Three indexes:
  - (session_id, timestamp DESC) — primary index covering the page
    query (FR-001).
  - (session_id, event_class) — supports future server-side type
    filter (v1 keeps it client-side per FR-011).
  - (session_id, participant_id) — supports future server-side
    participant filter (same).

CHECK constraints enforce the fixed five-class taxonomy
(Clarifications §3 + §8) and the four-value disposition enum
(Clarifications §5) at the DB layer, fail-closed.

Revision ID: 017
Revises: 016
Create Date: 2026-05-11
"""

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create detection_events table + 3 indexes."""
    _create_table()
    _create_indexes()


def _create_table() -> None:
    op.execute("""
        CREATE TABLE detection_events (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            event_class TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            trigger_snippet TEXT,
            detector_score REAL,
            turn_number INTEGER,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            disposition TEXT NOT NULL DEFAULT 'pending',
            last_disposition_change_at TIMESTAMPTZ,
            CONSTRAINT detection_events_class_check CHECK (event_class IN (
                'ai_question_opened', 'ai_exit_requested', 'density_anomaly',
                'mode_recommendation', 'mode_change'
            )),
            CONSTRAINT detection_events_disposition_check CHECK (disposition IN (
                'pending', 'banner_acknowledged', 'banner_dismissed', 'auto_resolved'
            ))
        )
    """)


def _create_indexes() -> None:
    op.execute(
        "CREATE INDEX detection_events_session_timestamp_idx "
        "ON detection_events (session_id, timestamp DESC)"
    )
    op.execute(
        "CREATE INDEX detection_events_session_class_idx "
        "ON detection_events (session_id, event_class)"
    )
    op.execute(
        "CREATE INDEX detection_events_session_participant_idx "
        "ON detection_events (session_id, participant_id)"
    )


def downgrade() -> None:
    """Forward-only per Constitution §6 + 001 §FR-017."""
    pass
