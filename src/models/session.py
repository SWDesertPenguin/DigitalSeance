"""Session and Branch frozen dataclass models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Session:
    """A collaboration session — root entity for all SACP data."""

    id: str
    name: str
    created_at: datetime
    status: str
    current_turn: int
    last_summary_turn: int
    facilitator_id: str | None
    auto_approve: bool
    auto_archive_days: int | None
    auto_delete_days: int | None
    parent_session_id: str | None
    cadence_preset: str
    complexity_classifier_mode: str
    min_model_tier: str
    acceptance_mode: str
    review_gate_pause_scope: str
    length_cap_kind: str = "none"
    length_cap_seconds: int | None = None
    length_cap_turns: int | None = None
    conclude_phase_started_at: datetime | None = None
    active_seconds_accumulator: int | None = None

    @classmethod
    def from_record(cls, record: Any) -> Session:
        """Construct a Session from an asyncpg Record."""
        return cls(
            id=record["id"],
            name=record["name"],
            created_at=record["created_at"],
            status=record["status"],
            current_turn=record["current_turn"],
            last_summary_turn=record["last_summary_turn"],
            facilitator_id=record["facilitator_id"],
            auto_approve=record["auto_approve"],
            auto_archive_days=record["auto_archive_days"],
            auto_delete_days=record["auto_delete_days"],
            parent_session_id=record["parent_session_id"],
            cadence_preset=record["cadence_preset"],
            complexity_classifier_mode=record["complexity_classifier_mode"],
            min_model_tier=record["min_model_tier"],
            acceptance_mode=record["acceptance_mode"],
            review_gate_pause_scope=record["review_gate_pause_scope"],
            length_cap_kind=_field(record, "length_cap_kind", "none"),
            length_cap_seconds=_field(record, "length_cap_seconds", None),
            length_cap_turns=_field(record, "length_cap_turns", None),
            conclude_phase_started_at=_field(record, "conclude_phase_started_at", None),
            active_seconds_accumulator=_field(record, "active_seconds_accumulator", None),
        )


def _field(record: Any, key: str, default: Any) -> Any:
    """Read an optional column; tolerate older records lacking the field."""
    try:
        return record[key]
    except (KeyError, IndexError):
        return default


@dataclass(frozen=True, slots=True)
class Branch:
    """A conversation thread within a session."""

    id: str
    session_id: str
    parent_branch_id: str | None
    branch_point_turn: int
    name: str
    status: str
    created_by: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> Branch:
        """Construct a Branch from an asyncpg Record."""
        return cls(
            id=record["id"],
            session_id=record["session_id"],
            parent_branch_id=record["parent_branch_id"],
            branch_point_turn=record["branch_point_turn"],
            name=record["name"],
            status=record["status"],
            created_by=record["created_by"],
            created_at=record["created_at"],
        )
