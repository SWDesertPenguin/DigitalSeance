# 0001. Fire-and-forget summarization

**Date**: 2026-04-30 (retrospective; decision originally landed in Phase 2 implementation 2026-04-XX)
**Status**: accepted

## Context and problem statement

Long-running SACP sessions accumulate enough context to threaten the per-participant token budget. Spec 005 (summarization checkpoints) calls for periodic summaries that compress prior history into a single message so subsequent turns stay within budget.

Where the summarization runs matters operationally. The summary is itself an LLM call (variable latency, occasionally seconds; can fail or rate-limit). If summarization runs synchronously inside the turn loop, every Nth turn pays a multi-second tax and a single provider hiccup stalls the whole session.

## Considered options

1. **Synchronous in-loop summarization** — turn N+50 blocks on the summary completing. Simplest to reason about; predictable failure mode (loop pauses, operator notices).
2. **Fire-and-forget async task** — summarization runs as `asyncio.create_task(...)`; turn loop continues immediately. Loop never blocks; failures are silent unless explicitly logged.
3. **Synchronous-with-timeout fallback** — try synchronously with a short timeout; on timeout, abandon and continue. Hybrid; keeps the summary on the same turn boundary while bounding the latency tax.

## Decision outcome

Chose **option 2 (fire-and-forget async task)** per spec 005 §FR-010.

The turn-loop never-halts invariant (003 §FR-021) is the dominant constraint. Adding a multi-second blocking step every N turns directly undermines it. Option 1 is architecturally simpler but conflicts with the invariant. Option 3 preserves the invariant under the happy path but reintroduces blocking under provider stress (the very condition that would make option 1 worst-case).

The fire-and-forget pattern accepts a different cost: summarization failures may go unnoticed if not explicitly surfaced. We mitigate via:

- Logging at WARNING level on every summarization exception (FR-008 fallback cascade).
- Operators can audit `messages` rows with `speaker_type='summary'` to confirm summaries are landing on schedule.
- Future Phase 3 trigger: surface a participant_health-style indicator if summarization rate falls below the threshold dictated by FR-001.

## Consequences

**Positive**:
- Turn loop never blocks on summary work — 003 §FR-021 invariant preserved.
- Provider hiccups affecting the cheapest-model participant don't stall the session.
- Summarization can be retried by the next checkpoint without operator intervention.

**Negative**:
- Failures are silent without explicit instrumentation (mitigated by logging + audit query).
- A summary triggered by turn N may not finish by turn N+1; the next turn's context may include "old" history beyond what the summarizer is currently compressing. Acceptable per FR-006 (summary trigger threshold gives runway).
- The `cheapest-participant-pays-for-all` cost model (FR-012) means one participant unilaterally pays for everyone's summary work; their budget can be exhausted by sessions they don't dominate. Trigger for re-evaluation: any operator complaint about asymmetric cost burden.

## Cross-references

- Spec 005 §FR-010 — fire-and-forget contract
- Spec 003 §FR-021 — turn-loop never-halts invariant
- Memory `feedback_exclude_humans_from_dispatch.md` — recurring bug class on summarizer dispatch (humans must be filtered out)
