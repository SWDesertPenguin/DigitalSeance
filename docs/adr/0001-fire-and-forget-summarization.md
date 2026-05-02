# ADR 0001 — Fire-and-forget summarization checkpoints

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-04-30 |
| Decision-makers | Facilitator |
| Format | MADR 4.0 (lightweight) |

---

## Context

The turn loop (spec 003) must dispatch each participant turn within its configured timeout
(default: 60 s per turn, compound retry cap 180 s per 003 §FR-031). Summarization
checkpoints (spec 005) trigger when the turn count crosses a configured threshold (default
every 50 turns) and involve one or more LLM calls plus a DB write; observed latency ranges
from 5 s (cheapest model, short transcript) to 30+ s (long context, slow provider).

Blocking the turn loop inline on summarization would:
- Extend every turn's wall-clock time by the summarizer's latency, violating the 003
  §FR-019 dispatch-time contract.
- Propagate summarizer failures (provider timeout, rate-limit, model unavailable) into
  the live turn loop, causing cascading circuit-breaker trips for unrelated participants.

## Decision

Summarization is launched as `asyncio.create_task()` immediately after the threshold
condition is detected. The turn loop records the task reference but does not await it;
the next turn dispatches without waiting for the summarizer to complete or fail.
See 005 §FR-010 for the formal spec of this contract.

## Consequences

**Positive**
- Turn-loop latency is fully decoupled from summarizer latency.
- Provider failures in the summarizer are isolated: they log, increment a counter, and
  do not propagate to the turn loop or trip participants' circuit breakers.
- The cheapest available participant is selected as the summarizer (005 §FR-007),
  minimising cost impact on other participants' budgets.

**Negative / accepted trade-offs**
- On SIGTERM the in-flight task is abandoned without a graceful drain (documented in
  005 §FR-010 as accepted behaviour; the turn loop restarts cleanly and re-evaluates
  the threshold on the next turn).
- Concurrent session deletion raises `ForeignKeyViolationError` in the summary INSERT,
  which is caught, logged, and treated as a no-op (005 §FR-015).
- The summarizer participant is charged for the LLM call even when the session ends
  immediately after trigger — cost is bounded to a single checkpoint call.

## Alternatives considered

**Await inline** — Rejected. Blocks the turn loop for the summarizer's latency window;
any provider timeout propagates as a turn failure.

**Dedicated background worker process** — Rejected for Phase 1/2 scope. Adds inter-process
coordination; the single-instance deployment assumption (ADR 0002, planned) makes this
unnecessary until multi-instance scale is targeted in Phase 3+.
