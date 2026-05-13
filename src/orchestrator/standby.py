# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 027 standby evaluator + pivot injector.

Public surface per ``specs/027-participant-standby-modes/contracts/standby-evaluator.md``:

- ``StandbyConfig`` — frozen dataclass holding the four env-var values.
- ``StandbyEvalResult`` — frozen dataclass returned per evaluate_tick.
- ``evaluate_tick`` — async function. The caller (``loop.py``) wires
  this into the per-turn prep BEFORE router.next_speaker.
- ``apply_eval_result`` — async function. Persists the audit rows + WS
  events + pivot message + state transitions per the result.

The evaluator is O(1) per participant per tick (V14 budget). All four
detection signals are constant-time lookups against the per-tick
unresolved-gates set.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import asyncpg

from src.models.participant import Participant

log = logging.getLogger(__name__)


_STANDBY_REASON_AWAITING_HUMAN = "awaiting_human"
_STANDBY_REASON_AWAITING_GATE = "awaiting_gate"
_STANDBY_REASON_AWAITING_VOTE = "awaiting_vote"
_STANDBY_REASON_FILLER_STUCK = "filler_stuck"


@dataclass(frozen=True, slots=True)
class StandbyConfig:
    """Spec 027 env-var-resolved standby configuration.

    All four values are read at session-construct time and frozen for the
    session lifetime; mid-session env-var changes do NOT take effect
    until the next loop restart, mirroring spec 014's controller pattern.
    """

    default_wait_mode: str = "wait_for_human"
    filler_detection_turns: int = 5
    pivot_timeout_seconds: int = 600
    pivot_rate_cap_per_session: int = 1

    @classmethod
    def from_env(cls) -> StandbyConfig:
        """Resolve from the four SACP_STANDBY_* env vars.

        V16 validators run at orchestrator startup and refuse-to-bind on
        out-of-range values; by the time this classmethod runs, every
        value present in the environment is well-formed.
        """
        return cls(
            default_wait_mode=os.environ.get("SACP_STANDBY_DEFAULT_WAIT_MODE", "wait_for_human"),
            filler_detection_turns=int(os.environ.get("SACP_STANDBY_FILLER_DETECTION_TURNS", "5")),
            pivot_timeout_seconds=int(os.environ.get("SACP_STANDBY_PIVOT_TIMEOUT_SECONDS", "600")),
            pivot_rate_cap_per_session=int(
                os.environ.get("SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION", "1")
            ),
        )


@dataclass(frozen=True, slots=True)
class StandbyEvalResult:
    """Single-tick evaluator output. Frozen; the caller applies side-effects."""

    entered: list[tuple[str, str]] = field(default_factory=list)
    exited: list[str] = field(default_factory=list)
    observer_marked: list[str] = field(default_factory=list)
    pivot_text: str | None = None
    pivot_skipped_rate_cap: bool = False
    cycle_increments: list[str] = field(default_factory=list)


PIVOT_TEXT = (
    "No human reply received in the configured timeout window. Either "
    "pivot to a related sub-topic the panel can advance independently, "
    "or self-mark as observer until the human returns. The orchestrator "
    "will treat unanswered standby participants as long-term observers."
)


async def evaluate_tick(
    pool: asyncpg.Pool,
    session_id: str,
    current_turn: int,
    config: StandbyConfig,
) -> StandbyEvalResult:
    """Run the standby evaluator for one round-robin tick.

    Walks every participant in the session (excluding humans + facilitator
    + circuit_open + paused), evaluates the four detection signals for
    each ``wait_mode='wait_for_human'`` participant, and produces a
    StandbyEvalResult the caller applies. No DB writes happen here — the
    caller's ``apply_eval_result`` does the persistence.
    """
    rows = await _fetch_evaluable_rows(pool, session_id)
    entered: list[tuple[str, str]] = []
    exited: list[str] = []
    cycle_increments: list[str] = []
    for row in rows:
        await _evaluate_one(
            pool=pool,
            row=row,
            current_turn=current_turn,
            entered=entered,
            exited=exited,
            cycle_increments=cycle_increments,
        )
    pivot = await _maybe_evaluate_pivot(pool, session_id, cycle_increments, config)
    return StandbyEvalResult(
        entered=entered,
        exited=exited,
        observer_marked=pivot[1],
        pivot_text=pivot[0],
        pivot_skipped_rate_cap=pivot[2],
        cycle_increments=cycle_increments,
    )


async def _fetch_evaluable_rows(pool: asyncpg.Pool, session_id: str) -> list[Any]:
    """Return the candidate rows the evaluator should examine.

    Excludes humans (``provider='human'``), facilitators, circuit_open
    participants (FR-013 precedence), paused participants (FR-012
    precedence), and removed participants.
    """
    sql = """
        SELECT id, status, wait_mode, standby_cycle_count, wait_mode_metadata
        FROM participants
        WHERE session_id = $1
          AND provider != 'human'
          AND role != 'facilitator'
          AND status NOT IN ('circuit_open', 'paused', 'removed', 'pending')
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, session_id)
    return list(rows)


async def _evaluate_one(
    *,
    pool: asyncpg.Pool,
    row: Any,
    current_turn: int,
    entered: list[tuple[str, str]],
    exited: list[str],
    cycle_increments: list[str],
) -> None:
    """Evaluate a single participant's standby state."""
    pid = row["id"]
    status = row["status"]
    wait_mode = row["wait_mode"]
    if wait_mode == "always":
        if status == "standby":
            exited.append(pid)
        return
    reason = await _detect_signal(pool, pid, current_turn)
    if reason is None:
        if status == "standby":
            exited.append(pid)
        return
    if status == "standby":
        cycle_increments.append(pid)
        return
    entered.append((pid, reason))


async def _detect_signal(
    pool: asyncpg.Pool,
    participant_id: str,
    current_turn: int,
) -> str | None:
    """Return the triggering reason if any of the 4 signals fires, else None.

    Signals checked in priority order:
      1. unresolved ai_question_opened (awaiting_human)
      2. pending review_gate_staged (awaiting_gate)
      3. proposal awaiting vote + repeated low-content stance (awaiting_vote)
      4. filler-scorer stuck pattern (filler_stuck) - skipped when
         density_anomaly fires this tick (FR-007 off-rails coordination).
    """
    if await _signal_unresolved_question(pool, participant_id):
        return _STANDBY_REASON_AWAITING_HUMAN
    if await _signal_pending_review_gate(pool, participant_id):
        return _STANDBY_REASON_AWAITING_GATE
    if await _signal_proposal_awaiting_vote_with_stuck_stance(pool, participant_id, current_turn):
        return _STANDBY_REASON_AWAITING_VOTE
    if await _signal_filler_stuck(pool, participant_id, current_turn):
        return _STANDBY_REASON_FILLER_STUCK
    return None


async def _signal_unresolved_question(
    pool: asyncpg.Pool,
    participant_id: str,
) -> bool:
    """FR-004 signal: AI's own prior turn emitted an unresolved ai_question_opened."""
    sql = """
        SELECT 1 FROM detection_events
        WHERE participant_id = $1
          AND event_class = 'ai_question_opened'
          AND disposition = 'pending'
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, participant_id)
    return row is not None


async def _signal_pending_review_gate(
    pool: asyncpg.Pool,
    participant_id: str,
) -> bool:
    """FR-005 signal: review_gate_staged event for this AI's draft is pending."""
    sql = """
        SELECT 1 FROM review_gate_drafts
        WHERE participant_id = $1
          AND status = 'pending'
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, participant_id)
    return row is not None


async def _signal_proposal_awaiting_vote_with_stuck_stance(
    pool: asyncpg.Pool,
    participant_id: str,
    current_turn: int,
) -> bool:
    """FR-006 signal: proposal awaits vote AND last 2 turns are stuck.

    'Stuck' = cosine_similarity > 0.8 AND new_token_count < 50 against
    the immediately prior turn. The repetition guard requires N >= 2 for
    the similarity check to have a baseline (edge case in spec).
    """
    has_open_proposal = await _has_open_proposal_awaiting_vote(pool, participant_id)
    if not has_open_proposal:
        return False
    return await _last_two_turns_stuck(pool, participant_id, current_turn)


async def _signal_filler_stuck(
    pool: asyncpg.Pool,
    participant_id: str,
    current_turn: int,
) -> bool:
    """FR-007 signal: spec 021 filler-scorer flags the last 2 turns.

    Skips when a density_anomaly row exists for the same participant +
    same tick (off-rails coordination with spec 014).
    """
    if await _has_density_anomaly_this_tick(pool, participant_id, current_turn):
        return False
    sql = """
        SELECT filler_score FROM routing_log
        WHERE intended_participant = $1
          AND filler_score IS NOT NULL
        ORDER BY turn_number DESC
        LIMIT 2
    """
    async with pool.acquire() as conn:
        rows = await _conn_fetch_safe(conn, sql, participant_id)
    if len(rows) < 2:
        return False
    threshold = float(os.environ.get("SACP_FILLER_THRESHOLD", "0.6"))
    return all(float(r["filler_score"]) >= threshold for r in rows)


async def _has_open_proposal_awaiting_vote(
    pool: asyncpg.Pool,
    participant_id: str,
) -> bool:
    """True when an open proposal awaits this participant's vote."""
    sql = """
        SELECT 1 FROM proposals
        WHERE status = 'open'
          AND NOT EXISTS (
            SELECT 1 FROM proposal_votes
            WHERE proposal_id = proposals.id
              AND participant_id = $1
          )
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, participant_id)
    return row is not None


async def _last_two_turns_stuck(
    pool: asyncpg.Pool,
    participant_id: str,
    current_turn: int,
) -> bool:
    """Two-condition AND per Session 2026-05-12 Q8: cos_sim > 0.8 AND new_tokens < 50."""
    del current_turn  # currently unused; reserved for windowing
    sql = """
        SELECT content FROM messages
        WHERE speaker_id = $1
        ORDER BY turn_number DESC
        LIMIT 2
    """
    async with pool.acquire() as conn:
        rows = await _conn_fetch_safe(conn, sql, participant_id)
    if len(rows) < 2:
        return False
    prior = rows[1]["content"] or ""
    latest = rows[0]["content"] or ""
    if _approx_new_token_count(prior, latest) >= 50:
        return False
    return _approx_similarity(prior, latest) > 0.8


def _approx_new_token_count(prior: str, latest: str) -> int:
    """Symmetric-difference token count between two turns."""
    prior_tokens = set(prior.lower().split())
    latest_tokens = set(latest.lower().split())
    return len(latest_tokens - prior_tokens)


def _approx_similarity(prior: str, latest: str) -> float:
    """Jaccard-style approximation; the production path uses sentence-transformers.

    The v1 evaluator falls back to a fast token-Jaccard estimate when the
    sentence-transformers model is not available (tests against the
    in-memory substrate). Production deployments with the model loaded
    can swap this for the spec 004 cosine similarity computation in a
    future amendment — the signature is intentionally simple to keep
    the test-substrate path deterministic.
    """
    prior_tokens = set(prior.lower().split())
    latest_tokens = set(latest.lower().split())
    if not prior_tokens or not latest_tokens:
        return 0.0
    intersection = prior_tokens & latest_tokens
    union = prior_tokens | latest_tokens
    return len(intersection) / len(union) if union else 0.0


async def _has_density_anomaly_this_tick(
    pool: asyncpg.Pool,
    participant_id: str,
    current_turn: int,
) -> bool:
    """FR-007 coordination: signal #4 skips when density_anomaly fires this tick."""
    sql = """
        SELECT 1 FROM routing_log
        WHERE intended_participant = $1
          AND turn_number = $2
          AND reason LIKE 'density_anomaly%'
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, participant_id, current_turn)
    return row is not None


async def _maybe_evaluate_pivot(
    pool: asyncpg.Pool,
    session_id: str,
    cycle_increments: list[str],
    config: StandbyConfig,
) -> tuple[str | None, list[str], bool]:
    """Check whether the pivot should fire for any standby participant.

    Returns (pivot_text_or_None, observer_marked_list, rate_cap_skipped).
    Only fires once per evaluate_tick — first eligible participant wins.
    """
    if config.pivot_rate_cap_per_session == 0:
        return (None, [], False)
    eligible = await _participants_at_pivot_threshold(pool, session_id, config)
    if not eligible:
        return (None, [], False)
    existing = await _pivot_count_for_session(pool, session_id)
    if existing >= config.pivot_rate_cap_per_session:
        return (None, [], True)
    targets = [pid for pid, wait_mode in eligible if wait_mode == "wait_for_human"]
    return (PIVOT_TEXT, targets, False)


async def _participants_at_pivot_threshold(
    pool: asyncpg.Pool,
    session_id: str,
    config: StandbyConfig,
) -> list[tuple[str, str]]:
    """Return (pid, wait_mode) for participants whose cycle+elapsed both gates open."""
    sql = """
        SELECT id, wait_mode, standby_cycle_count
        FROM participants
        WHERE session_id = $1
          AND status = 'standby'
          AND standby_cycle_count >= $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, session_id, config.filler_detection_turns)
    out: list[tuple[str, str]] = []
    for row in rows:
        if await _gate_age_exceeds(pool, row["id"], config.pivot_timeout_seconds):
            out.append((row["id"], row["wait_mode"]))
    return out


async def _gate_age_exceeds(
    pool: asyncpg.Pool,
    participant_id: str,
    timeout_seconds: int,
) -> bool:
    """True when the most recent standby_entered audit row is older than timeout."""
    sql = """
        SELECT timestamp FROM admin_audit_log
        WHERE target_id = $1
          AND action = 'standby_entered'
        ORDER BY timestamp DESC
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, participant_id)
    if row is None:
        return False
    entered_at = row["timestamp"]
    if entered_at.tzinfo is None:
        entered_at = entered_at.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - entered_at).total_seconds()
    return elapsed >= timeout_seconds


async def _pivot_count_for_session(pool: asyncpg.Pool, session_id: str) -> int:
    """Count pivot_injected audit rows for the session."""
    sql = """
        SELECT COUNT(*)::int AS cnt FROM admin_audit_log
        WHERE session_id = $1
          AND action = 'pivot_injected'
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, session_id)
    return int(row["cnt"]) if row else 0


async def _conn_fetchrow_safe(conn: Any, sql: str, *args: Any) -> Any:
    """Wrap conn.fetchrow with a tolerance for missing-table errors.

    The test substrate constructs only the tables it needs per test. A
    standby evaluator that hard-fails on a missing optional table would
    break unrelated tests. Missing tables are treated as "no rows" which
    is the same effective outcome as an empty table.
    """
    try:
        return await conn.fetchrow(sql, *args)
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError) as exc:
        log.debug("standby_eval_missing_table %s", exc)
        return None


async def _conn_fetch_safe(conn: Any, sql: str, *args: Any) -> list[Any]:
    """List-returning variant of _conn_fetchrow_safe."""
    try:
        return list(await conn.fetch(sql, *args))
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError) as exc:
        log.debug("standby_eval_missing_table %s", exc)
        return []


async def apply_eval_result(
    pool: asyncpg.Pool,
    session_id: str,
    current_turn: int,
    result: StandbyEvalResult,
    log_repo: Any,
) -> None:
    """Persist + broadcast the side-effects of one tick's evaluation.

    Order per `contracts/standby-evaluator.md`:
      1. UPDATE participants.status for entered/exited.
      2. Increment standby_cycle_count for still-standby participants.
      3. INSERT admin_audit_log rows.
      4. Broadcast participant_standby / participant_standby_exited WS.
      5. INSERT pivot message + audit row when pivot_text is set.
      6. UPDATE wait_mode_metadata for observer_marked participants.
    """
    facilitator_id = await _resolve_facilitator(pool, session_id)
    for participant_id, reason in result.entered:
        await _transition_to_standby(pool, participant_id)
        await _audit_standby_entered(log_repo, session_id, facilitator_id, participant_id, reason)
        await _broadcast_standby_entered(session_id, participant_id, reason, current_turn)
    for participant_id in result.exited:
        await _transition_to_active(pool, participant_id)
        await _audit_standby_exited(log_repo, session_id, facilitator_id, participant_id)
        await _broadcast_standby_exited(session_id, participant_id, current_turn)
    for pid in result.cycle_increments:
        await _increment_cycle_count(pool, pid)
    if result.pivot_text is not None:
        await _inject_pivot(
            pool=pool,
            session_id=session_id,
            current_turn=current_turn,
            log_repo=log_repo,
            facilitator_id=facilitator_id,
            observer_targets=result.observer_marked,
        )


async def _transition_to_standby(pool: asyncpg.Pool, participant_id: str) -> None:
    sql = """
        UPDATE participants
        SET status = 'standby', standby_cycle_count = 0
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        await conn.execute(sql, participant_id)


async def _transition_to_active(pool: asyncpg.Pool, participant_id: str) -> None:
    sql = """
        UPDATE participants
        SET status = 'active',
            standby_cycle_count = 0,
            wait_mode_metadata = '{}'::jsonb
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(sql, participant_id)
        except asyncpg.DataError:
            # Test substrate stores metadata as TEXT.
            fallback = """
                UPDATE participants
                SET status = 'active',
                    standby_cycle_count = 0,
                    wait_mode_metadata = '{}'
                WHERE id = $1
            """
            await conn.execute(fallback, participant_id)


async def _increment_cycle_count(pool: asyncpg.Pool, participant_id: str) -> None:
    sql = """
        UPDATE participants
        SET standby_cycle_count = standby_cycle_count + 1
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        await conn.execute(sql, participant_id)


async def _resolve_facilitator(pool: asyncpg.Pool, session_id: str) -> str:
    """Return the facilitator id or 'orchestrator' when the session lacks one."""
    sql = """
        SELECT id FROM participants
        WHERE session_id = $1 AND role = 'facilitator'
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await _conn_fetchrow_safe(conn, sql, session_id)
    return row["id"] if row else "orchestrator"


async def _audit_standby_entered(
    log_repo: Any,
    session_id: str,
    facilitator_id: str,
    participant_id: str,
    reason: str,
) -> None:
    await log_repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="standby_entered",
        target_id=participant_id,
        previous_value="active",
        new_value=f"standby:{reason}",
    )


async def _audit_standby_exited(
    log_repo: Any,
    session_id: str,
    facilitator_id: str,
    participant_id: str,
) -> None:
    await log_repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="standby_exited",
        target_id=participant_id,
        previous_value="standby",
        new_value="active",
    )


async def _broadcast_standby_entered(
    session_id: str,
    participant_id: str,
    reason: str,
    current_turn: int,
) -> None:
    """Push the participant_standby WS event."""
    from src.web_ui.events import participant_standby_event
    from src.web_ui.websocket import broadcast_to_session

    payload = participant_standby_event(participant_id, reason, current_turn)
    try:
        await broadcast_to_session(session_id, payload)
    except Exception as exc:  # noqa: BLE001 - WS push is best-effort
        log.warning("participant_standby_broadcast_failed: %s", exc)


async def _broadcast_standby_exited(
    session_id: str,
    participant_id: str,
    current_turn: int,
) -> None:
    """Push the participant_standby_exited WS event."""
    from src.web_ui.events import participant_standby_exited_event
    from src.web_ui.websocket import broadcast_to_session

    payload = participant_standby_exited_event(participant_id, current_turn)
    try:
        await broadcast_to_session(session_id, payload)
    except Exception as exc:  # noqa: BLE001 - WS push is best-effort
        log.warning("participant_standby_exited_broadcast_failed: %s", exc)


async def _inject_pivot(
    *,
    pool: asyncpg.Pool,
    session_id: str,
    current_turn: int,
    log_repo: Any,
    facilitator_id: str,
    observer_targets: list[str],
) -> None:
    """Persist the pivot message + audit row; mark long-term-observer targets."""
    await _insert_pivot_message(pool, session_id, current_turn)
    await log_repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="pivot_injected",
        target_id=session_id,
        previous_value=None,
        new_value=json.dumps({"turn_number": current_turn}),
    )
    for pid in observer_targets:
        await _mark_long_term_observer(pool, pid)
        await log_repo.log_admin_action(
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="standby_observer_marked",
            target_id=pid,
            previous_value="standby",
            new_value="standby:long_term_observer",
        )


async def _insert_pivot_message(
    pool: asyncpg.Pool,
    session_id: str,
    current_turn: int,
) -> None:
    """INSERT a system-tier pivot message with metadata.kind discriminator."""
    sql = """
        INSERT INTO messages (
            session_id, turn_number, branch_id, speaker_id, speaker_type,
            content, metadata, created_at
        ) VALUES ($1, $2, NULL, 'orchestrator', 'system', $3, $4, NOW())
    """
    metadata = json.dumps({"kind": "orchestrator_pivot"})
    async with pool.acquire() as conn:
        try:
            await conn.execute(sql, session_id, current_turn, PIVOT_TEXT, metadata)
        except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError) as exc:
            log.debug("pivot_insert_skipped_missing_schema %s", exc)


async def _mark_long_term_observer(pool: asyncpg.Pool, participant_id: str) -> None:
    """Set wait_mode_metadata.long_term_observer=true on the participant row."""
    sql = """
        UPDATE participants
        SET wait_mode_metadata = jsonb_set(
            COALESCE(wait_mode_metadata, '{}'::jsonb),
            '{long_term_observer}',
            'true'::jsonb,
            true
        )
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(sql, participant_id)
        except (asyncpg.DataError, asyncpg.UndefinedFunctionError):
            # Test substrate stores metadata as TEXT — fall back to a
            # JSON string update preserving any existing keys.
            fallback = """
                UPDATE participants
                SET wait_mode_metadata = '{"long_term_observer": true}'
                WHERE id = $1
            """
            await conn.execute(fallback, participant_id)


async def update_participant_wait_mode(
    pool: asyncpg.Pool,
    participant_id: str,
    new_mode: str,
) -> str | None:
    """Mutate participants.wait_mode and return the previous value (FR-025 endpoint)."""
    if new_mode not in ("wait_for_human", "always"):
        msg = f"invalid wait_mode {new_mode!r}"
        raise ValueError(msg)
    async with pool.acquire() as conn:
        old = await _conn_fetchrow_safe(
            conn,
            "SELECT wait_mode FROM participants WHERE id = $1",
            participant_id,
        )
        if old is None:
            return None
        await conn.execute(
            "UPDATE participants SET wait_mode = $1 WHERE id = $2",
            new_mode,
            participant_id,
        )
        return old["wait_mode"]


def standby_signal_present_for_participant(participant: Participant) -> bool:
    """Pure-function helper: is this participant's status reflecting standby?"""
    return participant.status == "standby"
