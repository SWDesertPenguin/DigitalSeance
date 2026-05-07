# Feature Specification: Summarization Checkpoints

**Feature Branch**: `005-summarization-checkpoints`
**Created**: 2026-04-11
**Status**: Draft
**Input**: User description: "Summarization checkpoints — structured JSON summaries every N turns capturing decisions, open questions, key positions, and narrative for context assembly"

## Clarifications

### Session 2026-05-02 (audit fix/005-reliability — Phase E)

- Q: What happens on SIGTERM if a summarization task is in flight? → A: Phase 1 abandoned. The fire-and-forget asyncio task (FR-010) is cancelled by uvicorn graceful-shutdown along with the loop coroutine; in-flight summarizations don't await completion. The next orchestrator startup re-evaluates the threshold via FR-001 — if the session has accumulated enough turns, the next eligible turn fires summarization again. No partial summary persists (transactional rollback).

- Q: What if FR-011 sanitize itself raises an exception during the recursive walk? → A: The exception propagates up to `run_checkpoint`'s outer handler and is logged with `WARNING: summarization failed during sanitize`; no summary row persists. This matches the 007 §FR-013 fail-closed contract — sanitize failure is treated identically to model failure. The session continues without a checkpoint; threshold re-evaluates on the next turn.

- Q: What's the operator manual-summarization override surface? → A: Phase 1: no dedicated kill switch / force-summarize / re-summarize-from-turn-N CLI. Operator workaround: facilitator can force a checkpoint by `UPDATE sessions SET last_summary_turn = current_turn - threshold` to make the next turn eligible. Phase 3 trigger: any deployment where operator-driven summarization control matters (e.g., regulatory replay scenarios); implementation: `/tools/admin/force_summarize?session_id=...&from_turn=N` endpoint.

- Q: How are existing pre-sanitize summaries audited? → A: PR #157 closed sanitize-recursion (FR-011) for NEW summaries; pre-sanitize summaries persist in the `messages` table with `speaker_type='summary'`. Operator audit query: `SELECT id, content FROM messages WHERE speaker_type='summary' AND created_at < '<sanitize-landed-date>';`. Re-sanitization of historic summaries is not automatic in Phase 1; Phase 3 trigger: any deployment where historical summary content represents recon risk; implementation: a one-shot script that walks pre-fix summaries through current sanitize and rewrites in-place (with audit-log entry).

### Session 2026-04-14

- Q: Non-blocking semantics? → A: Async task (asyncio.create_task fire-and-forget; loop proceeds immediately; summary lands whenever it finishes)
- Q: Cheapest-model selection when Ollama is present? → A: Prefer lowest cost among paid participants; fall back to free models only if no paid models exist (avoids always picking slow local)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Checkpoint Trigger (Priority: P1)

The orchestrator monitors the turn count since the last summarization checkpoint. When a configurable threshold is reached (default 50 turns), it triggers a summarization pass. The trigger is evaluated after each turn as part of the loop, but does not block the next turn — summarization can run asynchronously.

**Why this priority**: Without a trigger, checkpoints never fire. This is the activation mechanism.

**Independent Test**: Can be tested by advancing the turn counter past the threshold and verifying the trigger fires, then verifying it does not fire again until the next threshold.

**Acceptance Scenarios**:

1. **Given** a session at turn 49 with last_summary_turn = 0 and threshold = 50, **When** turn 50 completes, **Then** a summarization is triggered.
2. **Given** a summarization was just completed, **When** the next turn completes, **Then** no summarization is triggered until the threshold is reached again.
3. **Given** a configurable threshold, **When** the session is configured for 30-turn checkpoints, **Then** summarization fires every 30 turns.

---

### User Story 2 - Structured Summary Generation (Priority: P1)

When summarization is triggered, the system sends the accumulated turns (since the last checkpoint) to the cheapest available AI model with a prompt requesting structured JSON output. The expected output contains four sections: decisions made, open questions, key positions per participant, and a narrative overview.

**Why this priority**: The summary content is what gets used by context assembly. Without structured output, the summary is less useful for building coherent context.

**Independent Test**: Can be tested by providing a block of conversation turns and verifying the summarization prompt is sent to a cheap model and the response is parsed into the expected JSON structure.

**Acceptance Scenarios**:

1. **Given** accumulated turns since the last checkpoint, **When** summarization runs, **Then** the turns are sent to the cheapest available model with a structured summarization prompt.
2. **Given** a valid JSON summary response, **When** it is parsed, **Then** it contains decisions, open_questions, key_positions, and narrative sections.
3. **Given** an invalid JSON response from the model, **When** parsing fails, **Then** the system retries up to 3 times before falling back to storing the raw response as narrative-only.
4. **Given** a successful summary, **When** it is stored, **Then** it is persisted as a message with speaker_type='summary' and the session's last_summary_turn is updated.

---

### User Story 3 - Summary Storage and Retrieval (Priority: P1)

Completed summaries are stored as immutable messages in the transcript with speaker_type='summary'. The content field contains the structured JSON. The session's last_summary_turn field is updated to mark the checkpoint. Context assembly (feature 003) already reads summaries — this story ensures they are stored in the correct format.

**Why this priority**: Storage in the correct format is required for context assembly to parse and use the summaries.

**Independent Test**: Can be tested by generating a summary, storing it, and verifying it can be retrieved via the existing get_summaries method with correct JSON content.

**Acceptance Scenarios**:

1. **Given** a completed summary, **When** it is stored, **Then** a message is created with speaker_type='summary', speaker_id='system', and content containing valid JSON.
2. **Given** a stored summary, **When** retrieved via get_summaries, **Then** the JSON can be parsed into decisions, open_questions, key_positions, and narrative.
3. **Given** a stored summary, **When** the session is queried, **Then** last_summary_turn reflects the turn number of the latest checkpoint.

---

### User Story 4 - Cross-Model Checkpoint Compatibility (Priority: P2)

The summarization prompt must work across different model families (Claude, GPT, Llama, Mistral). The system uses the cheapest available model for cost efficiency but falls back to other models if the cheap model fails. The prompt is designed to produce valid JSON from models with varying JSON capabilities.

**Why this priority**: SACP is multi-model by design. Summaries that only work with one provider defeat the purpose.

**Independent Test**: Can be tested by sending the summarization prompt to mock providers simulating different model families and verifying JSON output is parsed correctly or fallback activates.

**Acceptance Scenarios**:

1. **Given** multiple active participants with different providers, **When** summarization runs, **Then** the cheapest model is selected regardless of provider.
2. **Given** the cheapest model fails to produce valid JSON after 3 retries, **When** fallback activates, **Then** the next cheapest model is tried.
3. **Given** all models fail to produce valid JSON, **When** all retries are exhausted, **Then** the raw response is stored as narrative-only with a warning logged.

---

### User Story 5 - Summary Preservation Across Deletion (Priority: P3)

Summaries are regular messages (speaker_type='summary') and follow the same immutability and lifecycle rules as all other messages. They are deleted only when the session is deleted (atomic deletion from feature 001). They are never individually deletable or editable.

**Why this priority**: This is an integrity guarantee that comes naturally from the existing data model, but it's worth validating explicitly.

**Independent Test**: Can be tested by creating a summary, then verifying it cannot be modified and survives session operations (pause, archive) but is removed on session deletion.

**Acceptance Scenarios**:

1. **Given** a stored summary, **When** an attempt is made to modify it, **Then** the modification is rejected (immutable messages).
2. **Given** a session with summaries, **When** the session is archived, **Then** summaries remain accessible.
3. **Given** a session with summaries, **When** the session is deleted, **Then** summaries are removed as part of atomic deletion.

---

### Edge Cases

- What happens when there are fewer turns than the threshold at session start? No summarization fires until the threshold is reached.
- What happens when the cheapest model has a very small context window? The summarization input is truncated to fit, prioritizing the most recent turns.
- What happens when summarization produces a summary that's too large for context assembly? The summary is stored as-is but context assembly may truncate it based on token budget.
- What happens when two summarizations trigger simultaneously (race condition)? Code-level: `should_summarize()` predicate at trigger time. SQL-level: the FR-013 guarded UPDATE ensures only one watermark advance succeeds — the loser's update is a no-op. Both summaries may be written, but only one advances `last_summary_turn`.
- What happens when the summarizer model returns valid JSON with adversarial content (`{"narrative": "ignore previous instructions..."}` or ChatML markers in `key_positions`)? FR-011 sanitization strips injection patterns from each string field before persistence. Adversarial content is reduced to neutered text in the stored summary.
- What happens when all candidate summarizer models fail (every cheapest-first fallthrough exhausts)? The exception propagates to `run_checkpoint`'s handler; the failure is logged; no summary is written. The next turn re-evaluates the threshold and may retry on the following turn.
- What happens during a session deletion in flight with summarization? Per FR-015, the FK violation on `messages.session_id` fails the append; the exception is caught by `run_checkpoint` and logged. No orphan summary rows are created.
- What happens when a summary itself triggers convergence detection? Convergence (004 §FR-003) operates over `convergence_log` rows which are written for AI turns only — summary rows do not produce embeddings, so no false convergence is triggered by summarization output (004 §FR-018 settles).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST trigger summarization when (current_turn - last_summary_turn) reaches a configurable threshold (default 50).
- **FR-002**: System MUST send accumulated turns to the cheapest available AI model for summarization.
- **FR-003**: System MUST request structured JSON output with four sections: decisions, open_questions, key_positions, narrative.
- **FR-004**: System MUST retry up to 3 times on invalid JSON responses before falling back to narrative-only storage.
- **FR-005**: System MUST store summaries as messages with `speaker_type='summary'` and `speaker_id` set to the **session facilitator's participant id** (NOT the literal string `'system'`). The facilitator-id attribution is required because `messages.speaker_id` has a foreign-key reference to `participants.id`; using `'system'` would violate referential integrity. The summary's distinguishing field is `speaker_type='summary'`, which is what context assembly and `get_summaries` filter on.
- **FR-006**: System MUST update session.last_summary_turn after each successful checkpoint.
- **FR-007**: System MUST select the cheapest model by comparing cost_per_input_token across active participants. Selection order: (1) lowest cost_per_input_token where cost > 0; (2) only if no paid models exist, fall back to free/null-cost participants (e.g., Ollama). This prevents summarization from always routing to slow local models.
- **FR-008**: System MUST fall back to the next cheapest model if the primary fails after retries.
- **FR-009**: System MUST log a warning when falling back to narrative-only storage.
- **FR-010**: System MUST not block the turn loop during summarization. Summarization MUST run as an `asyncio.create_task` fire-and-forget coroutine — the loop advances to the next turn immediately without waiting for the summary to complete.
- **FR-011**: System MUST treat summarizer model output as untrusted AI content. Before persistence, each string field of the parsed JSON (decisions, open_questions, key_positions, narrative — recursively) MUST pass through 007 §FR-001 sanitization (ChatML / role-marker / override-phrase / invisible-Unicode strip) AND 007 §FR-008 exfiltration filtering (credential redaction). A poisoned summary persists indefinitely and gets injected into every future participant's context, so it's a high-leverage indirect-injection target. If the input doesn't parse as JSON, the entire raw string is sanitized as a single block (matching the narrative-only fallback shape).
- **FR-012**: The summarizer's API key is the **cheapest active AI participant's** `api_key_encrypted`. This means the cheapest-model participant's quota pays for summaries on behalf of the whole session. This is accepted residual: the cheapest participant has the lowest per-call cost so the asymmetry is bounded; alternative designs (split cost across all participants, dedicated summarizer credential) are deferred to Phase 3.
- **FR-013**: The `last_summary_turn` race guard MUST be enforced at the SQL layer via `UPDATE sessions SET last_summary_turn = $1 WHERE id = $2 AND last_summary_turn < $1`. Two concurrent summarizations crossing the threshold near-simultaneously are deduplicated by this forward-only update — the second one's UPDATE is a no-op, preventing the second checkpoint from regressing the watermark.
- **FR-014**: Narrative-only fallback (FR-004) wraps the entire raw model response as the `narrative` field of an otherwise-empty structured summary. There is NO truncation of the raw response in Phase 1 — the message-immutability budget (001 §FR-007) and context-assembly token budget (003 §FR-004) bound the practical impact. If the response approaches 100KB, downstream context truncation discards excess silently.
- **FR-015**: An in-flight summarization that targets a session deleted between trigger and persistence MUST fail closed via the `messages.session_id` FK to `sessions(id)` (001 §FR-009). The asyncpg `ForeignKeyViolationError` is caught by `run_checkpoint`'s outer handler and logged. No orphan summary rows are created.

### Key Entities

- **Summarization Checkpoint**: A structured JSON message stored as speaker_type='summary'. Contains decisions (with turn references and status), open questions, per-participant key positions, and a narrative overview.
- **Summary Trigger**: Logic that evaluates whether the turn count threshold has been reached since the last checkpoint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Summarization fires within 1 turn of the threshold being reached.
- **SC-002**: 90%+ of summarization attempts produce valid structured JSON on the first try (well-designed prompt).
- **SC-003**: Summaries are retrievable via get_summaries and parseable into the expected 4-section structure.
- **SC-004**: The turn loop is never blocked by summarization — it completes within the same turn cycle or runs asynchronously.
- **SC-005**: Cheapest model selection correctly identifies the lowest-cost participant across providers.

## Assumptions

- The summarization prompt is a constant string in Phase 1. Prompt optimization is a future iteration.
- "Cheapest model" is determined by cost_per_input_token from the participants table. Paid participants (cost > 0) are preferred over free/null-cost participants; only if no paid models are available does selection fall back to free models (avoiding slow local models for a hot-path operation like summarization).
- Summarization runs using the existing ProviderBridge from feature 003. No new provider integration needed.
- The summary JSON schema is: `{"decisions": [...], "open_questions": [...], "key_positions": [...], "narrative": "..."}`. Schema validation is lenient — missing fields default to empty arrays/strings.
- Summary epoch tracking (message.summary_epoch field) groups messages under their checkpoint. The epoch increments with each checkpoint.
- Context assembly (feature 003) already reads summaries via MessageRepository.get_summaries. This feature ensures summaries are written in the format context assembly expects.

## Threat model traceability

| FR | Defends against | OWASP LLM | NIST AI 100-2 / SP 800-53 |
|----|-----------------|-----------|----------------------------|
| FR-001, FR-006, FR-013 (threshold + watermark + race guard) | Double-summarization / regression | — | SI-7 |
| FR-002, FR-007, FR-012 (cheapest-model selection) | Excessive summarization cost / supply-chain (untrusted free model) | LLM03, LLM04 | SC-5 |
| FR-003 (structured JSON output) | Unstructured / unparseable summary | — | SI-10 |
| FR-004, FR-008, FR-014 (retry + fallback) | Garbage summary blocking checkpoints | — | SI-13 |
| FR-005 (immutable storage) | Summary tampering | — | AU-9, SI-7 |
| FR-009 (warning on fallback) | Silent degradation | — | AU-2 |
| FR-010 (non-blocking) | Loop starvation / DoS | API4 | SC-5 |
| FR-011 (sanitize summary output) | Indirect prompt injection via summary content | LLM01, LLM05 | AI 100-2 §3.4; SI-15 |
| FR-015 (FK fail-closed on deletion race) | Orphan summary write to deleted session | — | SI-7 |

Sister cross-references: summary fields go through 007 §FR-001 sanitization + §FR-008 exfiltration filtering at `_store_summary` time; the message FK to sessions (001 §FR-009) provides fail-closed deletion-race protection (FR-015); `convergence_log` does not embed summaries (004 §FR-018) so summaries don't perturb convergence detection.

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 38 findings; resolution split:

**Code changes**: CHK001 / CHK003 / CHK007 (summary string fields recursively sanitized + exfiltration-filtered before persistence — `_sanitize_summary_content` + `_clean_node` in `src/orchestrator/summarizer.py`); CHK008 (`_update_session_turn` SQL guard `WHERE last_summary_turn < $1` so concurrent summarizations can't regress the watermark). New tests in `tests/test_summarizer.py` lock the contract.

**Spec amendments (this commit)**: CHK001 / CHK003 / CHK007 (FR-011 codifies sanitization mandate), CHK002 (FR-012 documents cheapest-model trust + cost asymmetry as accepted residual), CHK004 (FR-012 names the API-key source — cheapest participant's encrypted key), CHK005 (FR-014 narrative-only fallback wraps entire raw response), CHK008 (FR-013 SQL race guard mandate), CHK009 (FR-015 FK fail-closed on deletion race), CHK030 (Threat-model traceability table), CHK037 (FR-005 corrected to facilitator-id attribution + reason).

**Closed as cross-reference / accepted residual**: CHK006 (lenient JSON parsing — accepted convenience; missing fields default to empty arrays/strings), CHK010 (orphan async tasks — `run_checkpoint` is awaited inside the loop; not fire-and-forget at session-shutdown granularity), CHK011 / CHK013 (immutability + visibility cross-ref to 001 + 010), CHK012 (no per-row tamper hash — accepted residual; cross-row chaining is Phase 3), CHK014 / CHK015 (cheapest-model tie-breaking + threshold scope — implementation detail), CHK016 (JSON schema authoritativeness — pinned in `SUMMARIZATION_PROMPT` constant), CHK017 (summary consumes a turn_number — yes, by design, gives chronological ordering), CHK018 / CHK019 (cross-ref 003 + 007), CHK020 / CHK021 (90%+ valid JSON / cheapest-selection — measurement deferred), CHK022 (negative-path SCs — implicit), CHK023 / CHK024 / CHK025 (recovery / repeat-failure / fallback exhaustion — accepted: failure logged + retry on next turn), CHK026 (input truncation contract — accepted; LiteLLM truncates per-model context window), CHK027 (summary-induced convergence — settled by 004 §FR-018), CHK028 (all-models-fail fallback — accepted: skip checkpoint), CHK029 (adversarial `key_positions` content — settled by FR-011 sanitization), CHK031 / CHK032 (perf SLA / observability — accepted residual), CHK033 (ProviderBridge cost contract — covered by 003 §FR-006), CHK034 (prompt-version pinning — `SUMMARIZATION_PROMPT` constant + `# noqa` history is the version trail), CHK035 (`summary_epoch` overflow — INTEGER type, ~2.1B max; accepted), CHK036 (paid-vs-free preference — `_cost_key` treats `None` as +inf so unpriced participants are last), CHK038 (fallback-warn to security_events — accepted: routed through standard logger; not a security event in the 007 sense).

## Reliability (Phase E fix/005-reliability, 2026-05-02)

This section documents 005's failure-mode behavior for summarization. Operator-facing recovery procedures live in `docs/operational-runbook.md`; this section covers the contracts.

### Fallback-cascade exhaustion (FR-008)

Cheapest-model summarization fails → next-cheapest (FR-008) → repeat until participants exhausted. When ALL participants' models fail:

1. Each attempt logs `WARNING: summarization model X failed`
2. Final attempt logs `WARNING: summarization fell back to narrative-only` (per FR-009) OR if narrative-only also unparseable, `WARNING: summarization skipped — all models failed`
3. The loop continues normally — summarization is fire-and-forget per FR-010
4. The next eligible turn re-evaluates the threshold; if still over, summarization fires again

Operator notification: WARNING-level log emission. No `security_events` row (this is operational, not security). Operator alert: rolling-window summarization-failure rate per session > 50% over 1 hour indicates persistent degradation.

### In-flight checkpoint on session deletion (FR-015)

When a session is deleted between summarization trigger and persistence:

1. The async task continues running (orchestrator-level; no per-task cancellation on session delete)
2. INSERT INTO messages with `session_id=<deleted>` raises `asyncpg.ForeignKeyViolationError` (cross-ref 001 §FR-009 FK)
3. `run_checkpoint`'s outer handler catches and logs `WARNING: summarization target session deleted in-flight`
4. No orphan summary row is created (FK enforcement at the DB layer)

Operator-side observability: a small log volume of these WARNINGs after a session deletion is normal and benign.

### All-providers-fail behavior

Loop continues; summarization skipped (per FR-008 cascade exhaustion). Operator notification per FR-009 WARNING. No automatic retry beyond the in-task cascade — the session simply runs without an updated checkpoint until the next eligible turn.

Phase 3 trigger: any deployment where summarization-skip rate would degrade context quality enough to affect SLAs. Implementation surface: per-session "stale checkpoint" alert via `routing_log` query.

### Concurrent-checkpoint deduplication (FR-013)

Two coroutines crossing the threshold near-simultaneously:

1. Both call `_should_summarize` and observe the threshold met
2. Both dispatch summarization work → both pay the LLM call cost
3. The first to complete runs `UPDATE sessions SET last_summary_turn = $1 WHERE id = $2 AND last_summary_turn < $1` — succeeds, message INSERT proceeds
4. The second runs the same UPDATE — no-op (the condition `last_summary_turn < $1` is now false). Message INSERT NOT skipped — both summary rows persist with `speaker_type='summary'`

Wasted-LLM-call cost: bounded by 2× the per-summary cost (one duplicate per concurrent crossing). Phase 3 trigger: any deployment where the duplicate cost is meaningful at scale; implementation surface: pre-flight dedup via a `summary_in_progress` row lock or advisory lock per session.

### Summary-table corruption recovery

A malformed summary row (e.g., `content` field has invalid JSON despite passing FR-004 retry) is loaded by context assembly:

1. `get_summaries` returns the row
2. Context assembly's JSON parse fails → falls back to treating `content` as raw narrative (per FR-014 narrative-only contract)
3. Loop continues; subsequent dispatches proceed with degraded summary context

No automatic recovery in Phase 1. Operator manual recovery: identify the bad row via `SELECT id, length(content), content FROM messages WHERE speaker_type='summary' AND id = ...;`, DELETE the row, force a new checkpoint via the workaround in Clarifications.

### FR-010 fire-and-forget shutdown

On SIGTERM:

1. uvicorn graceful-shutdown signal cancels the loop coroutine
2. Fire-and-forget summarization tasks (`asyncio.create_task`) are cancelled
3. Cancelled tasks raise `asyncio.CancelledError`; transactional context rolls back any partial state
4. No summary row persists for cancelled tasks

Startup recovery: per-task is not resumed; the session's `last_summary_turn` reflects the last successful checkpoint. Threshold re-evaluation on the next turn.

### FR-011 sanitize-recursion failure

If sanitize raises an exception during the recursive walk (regex pathology, encoding error):

1. The exception propagates up to `run_checkpoint`'s outer handler
2. Logged at WARNING; no summary row persists
3. Treated identically to model failure (fail-closed per 007 §FR-013)
4. Threshold re-evaluates on the next turn

Cross-ref 007 Operations "Pipeline-bypass paths" — sanitize-recursion shares the root-logger ScrubFilter with 007 §FR-012 + 008 §FR-010.

### Cross-references

- `docs/operational-runbook.md` — operator playbook (cross-ref §6 provider degradation, §12 security pipeline ops)
- 001 §FR-009 — `messages.session_id` FK to `sessions(id)` (in-flight delete protection)
- 003 Reliability section — turn-loop reliability (sister)
- 003 §FR-021 — loop never halts on single-task failure
- 005 §FR-008, FR-009 — fallback cascade + narrative-only logging
- 005 §FR-010 — fire-and-forget task model
- 005 §FR-011 — sanitize recursion (cross-ref 007)
- 005 §FR-013 — SQL race-guard for concurrent checkpoints
- 005 §FR-014 — narrative-only fallback shape
- 005 §FR-015 — FK-protected in-flight delete
- 006 Reliability section — MCP-server reliability (sister)
- 007 §FR-013 — fail-closed pipeline contract

## Operational notes (Phase F amendment, 2026-05-02)

These items capture operator-facing decisions for summarization in
production. Sourced from the pre-Phase-3 audit window's operations review.

**Summarizer-model preference order.** FR-007 selects the cheapest paid
model first; null-cost (e.g., Ollama) participants are ranked last. There
is NO operator override in Phase 1 — the cost-sort key is structural
(via `_cost_key` in `src/orchestrator/summarizer.py`). Operators that
want a specific participant to summarize should ensure that participant
has the lowest non-null `cost_per_input_token`. Phase 3+ may expose a
dedicated summarizer participant role.

**Fallback-cascade depth bound.** `_generate_summary` walks every
cost-sorted candidate on `ProviderDispatchError`. The depth is bounded by
the participant count; for sessions with 10+ AI participants, a sustained
provider-side outage could trigger 10+ retries per checkpoint. Each
attempt does its own LiteLLM 3-retry loop, so worst-case attempt count is
`participants × 3 × json-validity-retries(3) ≈ 90` model calls per
failed checkpoint. Operators monitoring sustained failures should
quarantine bad participants via revoke or pause rather than relying on
the cascade to drain.

**All-models-fail behaviour.** When every candidate raises
`ProviderDispatchError` the final exception propagates and `run_checkpoint`
logs at WARNING. The next turn's threshold check re-fires the checkpoint
attempt — there is no exponential backoff between failed checkpoints
because the cost is already bounded by the threshold spacing
(default 10 turns). Operator visibility: monitor structured logs for
`Summarizer dispatch failed` warnings; sustained failure = paged signal.

**Operator manual-summarization override.** Phase 1 ships no manual
trigger — summarization fires only on threshold. There is no
`/tools/force_summarize` endpoint, no re-summarize-from-turn-N capability.
Operators wanting to force a checkpoint can advance `current_turn` past
the threshold via injected messages, OR wait for the natural cadence.
Phase 3 trigger: any deployment where operators routinely need to force
checkpoints (e.g., for audit closeout).

**Summary-content audit.** Auto-generated summaries persist as
immutable messages with `speaker_type='summary'`. Facilitators reviewing
auto-summaries can use `/tools/debug/export` (010) to dump the session
and `jq '.messages[] | select(.speaker_type == "summary")'` to extract
the canonical summary stream. Phase 3 may add a dedicated summary-review
UI surface in 011 web-ui.

**Threshold tuning (FR-001).** `DEFAULT_THRESHOLD=10` turns ships as the
Phase 1 default. Lowering toward 5 increases per-checkpoint LLM cost
(more checkpoints, each with the full window-since-last-summary). Raising
toward 50 reduces cost but increases the per-summary LLM context-window
requirement (the summarizer model must hold all unsummarized turns).
Operators with cheap, large-context models (e.g., Gemini Pro 2M) can
raise; operators with expensive small-context models should keep the
default.

**Narrative-only fallback rate alerting.** FR-014 wraps a non-JSON
response as narrative-only. A high rate of narrative-only fallbacks
indicates the summarizer model isn't following the JSON schema — quality
signal is degraded. Operators should alert on
`narrative-only-fallback rate > 10%` over 1h sustained. Action:
investigate whether the cheapest model has changed its instruction-
following behaviour, or rotate to a different summarizer model.

**Cheapest-participant rate-limit asymmetry.** Per FR-012 the cheapest
active AI participant's API key pays for every checkpoint. That
participant is also subject to the standard 009 rate limit (60 req/min).
Sessions running >60 checkpoints/min would saturate the cheapest
participant's window — but the threshold spacing makes this practically
impossible for the default 10-turn threshold (one checkpoint per ~10
turns is far below the rate ceiling). Operators with custom thresholds
< 1 should verify the rate-limit interaction.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): Topologies 1–6 only (orchestrator-driven). Summarization is triggered and executed by the orchestrator after turn N. Topology 7 (client-side AI) has no central summarizer; peer summary coordination is deferred to Phase 2+.

**Use cases** (per constitution §1): Serves all use cases that involve long sessions or knowledge-intensive collaboration — research co-authorship, consulting, and technical audits — where token budgets necessitate periodic compression without losing continuity.
