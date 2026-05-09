"""Data types for orchestrator operations.

Spec 020 relocates `ProviderResponse` to `src.api_bridge.adapter` (the
canonical home for SACP <-> adapter boundary types). The class is
re-exported here so existing imports
(`from src.orchestrator.types import ProviderResponse`) continue to
work without churning every call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.api_bridge.adapter import ProviderResponse as ProviderResponse  # noqa: F401

# Spec 025 FR-001 / data-model.md "LoopState (existing FSM, extended)":
# `conclude` is the new state alongside the existing running / paused /
# stopped. Existing call sites read the string column directly; this
# Literal exists for new code added by spec 025.
LoopState = Literal["running", "conclude", "paused", "stopped"]


# Spec 025 / contracts/routing-log-reasons.md:
# Five new `routing_log.reason` enum entries. Existing reasons used elsewhere
# in the codebase remain free-form strings; this Literal documents the
# spec 025 additions and is the authoritative shape for new emissions.
LengthCapRoutingReason = Literal[
    "cap_set",
    "conclude_phase_entered",
    "conclude_phase_exited",
    "auto_pause_on_cap",
    "manual_stop_during_conclude",
]


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


# `ProviderResponse` lives in `src.api_bridge.adapter` per spec 020;
# re-exported above for back-compat.
