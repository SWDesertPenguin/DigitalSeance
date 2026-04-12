"""Participant frozen dataclass model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Participant:
    """A human + AI collaborator within a session."""

    id: str
    session_id: str
    display_name: str
    role: str
    provider: str
    model: str
    model_tier: str
    prompt_tier: str
    model_family: str
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    domain_tags: str
    routing_preference: str
    observer_interval: int
    burst_interval: int
    review_gate_timeout: int
    turns_since_last_burst: int
    turn_timeout_seconds: int
    consecutive_timeouts: int
    status: str
    budget_hourly: float | None
    budget_daily: float | None
    max_tokens_per_turn: int | None
    cost_per_input_token: float | None
    cost_per_output_token: float | None
    system_prompt: str
    api_endpoint: str | None
    api_key_encrypted: str | None
    auth_token_hash: str | None
    last_seen: datetime | None
    invited_by: str | None
    approved_at: datetime | None
    token_expires_at: datetime | None
    bound_ip: str | None

    @classmethod
    def from_record(cls, record: Any) -> Participant:
        """Construct a Participant from an asyncpg Record."""
        return cls(**{f: record[f] for f in cls.__slots__})
