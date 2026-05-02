"""US4: Operational logs — append-only enforcement and query tests."""

from __future__ import annotations

import asyncpg
import pytest

from src.repositories.log_repo import LogRepository
from src.repositories.session_repo import SessionRepository


@pytest.fixture
async def session_and_facilitator(
    pool: asyncpg.Pool,
) -> tuple[str, str]:
    """Create a session and return (session_id, facilitator_id)."""
    repo = SessionRepository(pool)
    session, participant, _ = await repo.create_session(
        "Log Test Session",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id


@pytest.fixture
def repo(pool: asyncpg.Pool) -> LogRepository:
    """Provide a LogRepository."""
    return LogRepository(pool)


async def test_log_routing_persists(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Routing log entries persist with all fields."""
    sid, pid = session_and_facilitator
    entry = await repo.log_routing(
        session_id=sid,
        turn_number=0,
        intended=pid,
        actual=pid,
        action="normal",
        complexity="low",
        domain_match=True,
        reason="default routing",
    )
    assert entry.session_id == sid
    assert entry.routing_action == "normal"
    assert entry.domain_match is True


async def test_log_routing_with_per_stage_timings(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Per-stage timing columns round-trip correctly (012 US6 / 003 §FR-030).

    Verifies the RoutingLog dataclass exposes the timing fields and that
    a RETURNING * row with non-NULL timing values deserializes without
    error. Pre-fix the dataclass was missing these fields, causing
    from_record() to crash whenever migration 008 timing columns were
    populated.
    """
    sid, pid = session_and_facilitator
    entry = await repo.log_routing(
        session_id=sid,
        turn_number=1,
        intended=pid,
        actual=pid,
        action="normal",
        complexity="low",
        domain_match=True,
        reason="timed routing",
        route_ms=12,
        assemble_ms=84,
        dispatch_ms=543,
        persist_ms=7,
        advisory_lock_wait_ms=2,
    )
    assert entry.route_ms == 12
    assert entry.assemble_ms == 84
    assert entry.dispatch_ms == 543
    assert entry.persist_ms == 7
    assert entry.advisory_lock_wait_ms == 2


async def test_log_usage_persists(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Usage log entries record token counts and cost."""
    _, pid = session_and_facilitator
    entry = await repo.log_usage(
        participant_id=pid,
        turn_number=0,
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.003,
    )
    assert entry.input_tokens == 500
    assert entry.output_tokens == 200
    assert entry.cost_usd == pytest.approx(0.003)


async def test_get_participant_cost_aggregation(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """get_participant_cost aggregates usage for budget enforcement."""
    _, pid = session_and_facilitator
    await repo.log_usage(
        participant_id=pid,
        turn_number=0,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
    )
    await repo.log_usage(
        participant_id=pid,
        turn_number=1,
        input_tokens=200,
        output_tokens=100,
        cost_usd=0.002,
    )
    total = await repo.get_participant_cost(pid, period="daily")
    assert total == pytest.approx(0.003)


async def test_log_convergence_persists(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Convergence log entries store embeddings and scores."""
    sid, _ = session_and_facilitator
    embedding = b"\x00" * 384  # MiniLM-L6 vector size
    entry = await repo.log_convergence(
        turn_number=0,
        session_id=sid,
        embedding=embedding,
        similarity_score=0.85,
    )
    assert entry.similarity_score == pytest.approx(0.85)
    assert entry.divergence_prompted is False


async def test_convergence_window_returns_recent(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """get_convergence_window returns most recent entries in order."""
    sid, _ = session_and_facilitator
    for i in range(5):
        await repo.log_convergence(
            turn_number=i,
            session_id=sid,
            embedding=b"\x00" * 384,
            similarity_score=0.5 + i * 0.1,
        )
    window = await repo.get_convergence_window(sid, window_size=3)
    assert len(window) == 3
    assert window[0].turn_number < window[1].turn_number


async def test_log_admin_action_persists(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Admin audit log records facilitator actions."""
    sid, pid = session_and_facilitator
    entry = await repo.log_admin_action(
        session_id=sid,
        facilitator_id=pid,
        action="approve_participant",
        target_id="some-participant",
        previous_value="pending",
        new_value="participant",
    )
    assert entry.action == "approve_participant"
    assert entry.previous_value == "pending"
    assert entry.new_value == "participant"


async def test_audit_log_history(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """get_audit_log returns all entries for a session."""
    sid, pid = session_and_facilitator
    await repo.log_admin_action(
        session_id=sid,
        facilitator_id=pid,
        action="approve_participant",
        target_id="p1",
    )
    await repo.log_admin_action(
        session_id=sid,
        facilitator_id=pid,
        action="remove_participant",
        target_id="p2",
    )
    entries = await repo.get_audit_log(sid)
    assert len(entries) == 2
    actions = [e.action for e in entries]
    assert "approve_participant" in actions
    assert "remove_participant" in actions


async def test_log_security_event_persists(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Security events are persisted with layer + findings + risk score."""
    sid, pid = session_and_facilitator
    entry = await repo.log_security_event(
        session_id=sid,
        speaker_id=pid,
        turn_number=-1,
        layer="output_validator",
        findings='["ChatML token", "Override phrase"]',
        risk_score=0.9,
        blocked=True,
    )
    assert entry.layer == "output_validator"
    assert entry.blocked is True
    assert entry.risk_score == pytest.approx(0.9)
    assert "ChatML token" in entry.findings


async def test_get_security_events_returns_chronological(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """get_security_events returns all events for a session in order."""
    sid, pid = session_and_facilitator
    await repo.log_security_event(
        session_id=sid,
        speaker_id=pid,
        turn_number=-1,
        layer="exfiltration",
        findings='["credential_redacted"]',
    )
    await repo.log_security_event(
        session_id=sid,
        speaker_id=pid,
        turn_number=-1,
        layer="pipeline_error",
        findings='["pipeline_exception"]',
        blocked=True,
    )
    events = await repo.get_security_events(sid)
    assert len(events) == 2
    layers = [e.layer for e in events]
    assert layers == ["exfiltration", "pipeline_error"]


async def test_facilitator_override_row_persists(
    repo: LogRepository,
    session_and_facilitator: tuple[str, str],
) -> None:
    """Spec 012 FR-006: facilitator_override rows persist override_reason + actor.

    Verifies the override audit trail required by Constitution §4.9
    approach (b) — a facilitator explicitly approving flagged content
    must have a logged justification that survives a DB round-trip.
    """
    sid, pid = session_and_facilitator
    entry = await repo.log_security_event(
        session_id=sid,
        speaker_id=pid,
        turn_number=3,
        layer="facilitator_override",
        findings='["override_phrase"]',
        risk_score=0.85,
        blocked=False,
        override_reason="Operator confirmed this is a test message, not a real override",
        override_actor_id=pid,
    )
    assert entry.layer == "facilitator_override"
    assert entry.blocked is False
    assert entry.override_reason == "Operator confirmed this is a test message, not a real override"
    assert entry.override_actor_id == pid
    assert entry.risk_score == pytest.approx(0.85)
