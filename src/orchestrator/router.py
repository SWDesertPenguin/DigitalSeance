"""Turn router — 8-mode routing with round-robin rotation."""

from __future__ import annotations

import asyncpg

from src.models.participant import Participant
from src.orchestrator.classifier import classify
from src.orchestrator.types import RoutingDecision
from src.repositories.participant_repo import ParticipantRepository


class TurnRouter:
    """Routes turns based on participant preferences."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        encryption_key: str,
    ) -> None:
        self._pool = pool
        self._repo = ParticipantRepository(pool, encryption_key=encryption_key)
        self._turn_index: dict[str, int] = {}

    async def next_speaker(
        self,
        session_id: str,
    ) -> Participant | None:
        """Round-robin through active non-facilitator participants."""
        all_participants = await self._repo.list_participants(
            session_id,
            status_filter="active",
        )
        participants = [p for p in all_participants if p.role != "facilitator"]
        if not participants:
            return None
        idx = self._turn_index.get(session_id, 0)
        idx = idx % len(participants)
        self._turn_index[session_id] = idx + 1
        return participants[idx]

    async def route(
        self,
        participant: Participant,
        *,
        recent_text: str = "",
        has_interjection: bool = False,
    ) -> RoutingDecision:
        """Evaluate routing based on participant's preference."""
        complexity = classify(recent_text)
        mode = participant.routing_preference
        handler = _ROUTE_HANDLERS.get(mode, _route_always)
        return handler(participant, complexity, has_interjection)


def _route_always(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="normal",
        complexity=complexity,
        domain_match=True,
        reason="always mode",
    )


def _route_review_gate(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="review_gated",
        complexity=complexity,
        domain_match=True,
        reason="response staged for human review",
    )


def _route_delegate_low(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    if complexity == "low":
        return RoutingDecision(
            intended=p.id,
            actual=p.id,
            action="delegated",
            complexity=complexity,
            domain_match=True,
            reason="low complexity delegated",
        )
    return _route_always(p, complexity, _has_intr)


def _route_domain_gated(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    if complexity == "high":
        return _route_always(p, complexity, _has_intr)
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="skipped",
        complexity=complexity,
        domain_match=False,
        reason="low complexity, no domain match",
    )


def _route_burst(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    if p.turns_since_last_burst >= p.burst_interval:
        return RoutingDecision(
            intended=p.id,
            actual=p.id,
            action="burst_fired",
            complexity=complexity,
            domain_match=True,
            reason=f"burst fired after {p.burst_interval} turns",
        )
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="burst_accumulating",
        complexity=complexity,
        domain_match=True,
        reason="accumulating for burst",
    )


def _route_observer(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="skipped",
        complexity=complexity,
        domain_match=False,
        reason="observer mode — silent until switched",
    )


def _route_addressed_only(
    p: Participant,
    complexity: str,
    _has_intr: bool,
) -> RoutingDecision:
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="skipped",
        complexity=complexity,
        domain_match=False,
        reason="not addressed by name",
    )


def _route_human_only(
    p: Participant,
    complexity: str,
    has_intr: bool,
) -> RoutingDecision:
    if has_intr:
        return RoutingDecision(
            intended=p.id,
            actual=p.id,
            action="human_trigger",
            complexity=complexity,
            domain_match=True,
            reason="responding to human interjection",
        )
    return RoutingDecision(
        intended=p.id,
        actual=p.id,
        action="skipped",
        complexity=complexity,
        domain_match=False,
        reason="no human interjection pending",
    )


_ROUTE_HANDLERS = {
    "always": _route_always,
    "review_gate": _route_review_gate,
    "delegate_low": _route_delegate_low,
    "domain_gated": _route_domain_gated,
    "burst": _route_burst,
    "observer": _route_observer,
    "addressed_only": _route_addressed_only,
    "human_only": _route_human_only,
}
