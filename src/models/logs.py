"""Operational log frozen dataclass models — all append-only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RoutingLog:
    """Turn-by-turn routing decision record.

    Per-stage timing fields (003 §FR-030 + §FR-032) are nullable: they
    are NULL on skip-path rows that never reach dispatch, on rows written
    before the instrumentation landed, and for ``advisory_lock_wait_ms``
    on turns that acquired the lock without contention (sub-millisecond).
    """

    id: int
    session_id: str
    turn_number: int
    intended_participant: str
    actual_participant: str
    routing_action: str
    complexity_score: str
    domain_match: bool
    reason: str
    timestamp: datetime
    route_ms: int | None = None
    assemble_ms: int | None = None
    dispatch_ms: int | None = None
    persist_ms: int | None = None
    advisory_lock_wait_ms: int | None = None

    @classmethod
    def from_record(cls, record: Any) -> RoutingLog:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


@dataclass(frozen=True, slots=True)
class UsageLog:
    """Per-turn token count and cost record."""

    id: int
    participant_id: str
    turn_number: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime

    @classmethod
    def from_record(cls, record: Any) -> UsageLog:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


@dataclass(frozen=True, slots=True)
class ConvergenceLog:
    """Similarity measurement per turn."""

    turn_number: int
    session_id: str
    embedding: bytes
    similarity_score: float
    divergence_prompted: bool
    escalated_to_human: bool

    @classmethod
    def from_record(cls, record: Any) -> ConvergenceLog:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    """Security pipeline detection record (CHK008).

    Persists what each layer caught on a given turn, so attacks can be
    reviewed post-hoc without re-running the pipeline. ``layer`` is one
    of: ``output_validator``, ``exfiltration``, ``jailbreak``,
    ``prompt_protector``, ``pipeline_error``, ``facilitator_override``.
    ``findings`` is a JSON-encoded list of finding/flag/reason names from
    the layer.

    Spec 012 FR-006 (§4.9 approach (b)): when a facilitator explicitly
    overrides a flagged draft, a row is appended with
    ``layer="facilitator_override"``, ``blocked=False``,
    ``override_reason`` (the stated justification), and
    ``override_actor_id`` (the facilitator's participant id).
    """

    id: int
    session_id: str
    speaker_id: str
    turn_number: int
    layer: str
    risk_score: float | None
    findings: str
    blocked: bool
    timestamp: datetime
    layer_duration_ms: int | None = None
    override_reason: str | None = None
    override_actor_id: str | None = None

    @classmethod
    def from_record(cls, record: Any) -> SecurityEvent:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})


@dataclass(frozen=True, slots=True)
class AdminAuditLog:
    """Facilitator action record with before/after values."""

    id: int
    session_id: str
    facilitator_id: str
    action: str
    target_id: str
    previous_value: str | None
    new_value: str | None
    timestamp: datetime

    @classmethod
    def from_record(cls, record: Any) -> AdminAuditLog:
        """Construct from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})
