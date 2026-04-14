"""Data types for orchestrator operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TurnResult:
    """Outcome of a single turn execution."""

    session_id: str
    turn_number: int
    speaker_id: str
    action: str
    tokens_used: int
    cost_usd: float
    skipped: bool
    skip_reason: str | None
    delay_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """The routing determination for a turn."""

    intended: str
    actual: str
    action: str
    complexity: str
    domain_match: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """A formatted message for inclusion in a context payload."""

    role: str
    content: str
    source_turn: int | None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Response from an AI provider call."""

    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    latency_ms: int
