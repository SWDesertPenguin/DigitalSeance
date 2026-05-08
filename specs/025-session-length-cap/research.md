# Research: Session-Length Cap with Auto-Conclude Phase

**Branch**: `025-session-length-cap` | **Date**: 2026-05-07 | **Plan**: [plan.md](./plan.md)

Resolves the seven open decisions queued in [plan.md §"Phase 0 — Outline & Research"](./plan.md). Each section answers one question; each section closes with a Decision / Rationale / Alternatives format.

---

## §1 — `active_seconds` accumulator persistence

**Decision**: durable column on `sessions` (`active_seconds_accumulator: bigint | null`), updated by the orchestrator at each phase-transition event (running ↔ paused, running ↔ conclude, conclude → paused/stopped).

**Rationale**: the spec's pause-resume guarantee (FR-002, US2 acceptance #5) requires that wall-clock time elapsing during pause is NOT consumed against the time cap. An in-memory accumulator would lose state on orchestrator restart (Docker recreation, deploy, crash recovery), silently advancing the cap by the full clock between `started_at` and the post-restart `now()`. The durable column makes the spec's contract orchestrator-restart resilient. Cost is bounded: at most one UPDATE per FSM transition, not per-turn — well below the V14 budget for this stage. Concurrent UPDATEs on a single `sessions` row are serialized by Postgres row-level locking; no new contention surface.

**Alternatives considered**:
- **In-memory volatile** — cheapest at runtime but breaks pause-resume across restart; rejected as a correctness regression dressed up as a perf win.
- **Recomputed from `routing_log` history** — derives `active_seconds` by walking phase-transition events. Correct but O(transitions) per cap-check, which violates the V14 O(1)-per-dispatch budget. Acceptable as a forensic fallback / audit-trail double-check, but not as the hot-path source of truth.
- **Hybrid: durable checkpoint + in-memory delta** — track the durable accumulator + a since-last-checkpoint timestamp; sum at read time. Handles restart correctly with fewer writes, but introduces two sources of truth and a recovery-window edge case (orchestrator dies between durable update and now). The single durable column is simpler; one UPDATE per transition is fine.

---

## §2 — Cap-set endpoint shape

**Decision**: extend the existing session-settings endpoint (per spec 006 §FR-007) with `length_cap_*` fields. No new dedicated `/sessions/{id}/length_cap` resource.

**Rationale**: cap-set is conceptually a session-settings update. Spec 006's session-settings endpoint already has the facilitator-only authorization, the audit-log emission scaffolding, and the validation harness this feature needs. Adding a dedicated resource would duplicate authorization + audit code with no behavioral upside. The 409 disambiguation flow attaches naturally as a partial-update response on the same endpoint.

**Alternatives considered**:
- **Dedicated resource `/sessions/{id}/length_cap`** — cleaner OpenAPI grouping, but pure ceremony; same auth + audit + validation scaffolding gets reimplemented. Rejected.
- **Two endpoints (`PUT` for clean updates, separate `POST` for disambiguation)** — splits one logical operation into two HTTP surfaces and complicates the frontend's flow. Rejected; the 409 pattern keeps it as one operation with a branch.

---

## §3 — Disambiguation transport

**Decision**: 409 Conflict response carrying both interpretation options + idempotent re-POST with an explicit `interpretation` field on the same endpoint.

**Flow**:
1. Facilitator POSTs `{"length_cap_turns": 20}` to session-settings while at turn 30.
2. Orchestrator detects `submitted < current_elapsed`, returns 409 with body:
   ```json
   {
     "error": "cap_decrease_requires_interpretation",
     "current_elapsed": {"turns": 30, "seconds": null},
     "submitted": {"turns": 20},
     "options": {
       "absolute": {"effective_cap_turns": 20, "consequence": "immediate_conclude_phase"},
       "relative": {"effective_cap_turns": 50, "consequence": "loop_continues_until_trigger"}
     }
   }
   ```
3. Frontend (spec 011) renders a modal with the two options.
4. Facilitator picks one; frontend re-POSTs `{"length_cap_turns": 20, "interpretation": "absolute"}` (or `"relative"`).
5. Orchestrator commits the cap with the chosen interpretation, records `routing_log.cap_set` with `interpretation` field set.

**Rationale**: 409 makes the disambiguation a visible part of the protocol — clear contract, mechanical to test, matches HTTP semantics ("your request as stated cannot be processed without additional information"). Idempotent re-POST keeps the audit trail simple: only one row in `routing_log` per successful commit, no orphaned probe records. The `interpretation` field is rejected on calls where `submitted >= current_elapsed` (no decrease, no ambiguity), preserving a clean 200 path for the common case.

**Alternatives considered**:
- **Inline `interpretation` parameter on first call** — facilitator picks the interpretation upfront; orchestrator validates and commits in one call. Cleaner protocol, but pushes the disambiguation UI out of the cap-decrease moment (frontend has to anticipate the decrease). Rejected because the user-experience benefit of "the system tells you, you don't have to remember" is the entire reason the user requested disambiguation.
- **Two-phase probe + confirm with a transient token** — frontend probes the endpoint to learn the options, gets a token, posts the confirmation with the token. Solves a race condition (cap state changes between probe and confirm) but introduces token lifecycle management for a feature that doesn't need it. Rejected as over-engineered.

---

## §4 — Tier 4 composition with spec 021 register slider

**Decision**: forward-compatible attachment ordering captured as a documented contract in `src/prompts/tiers.py`. Tier 4 attaches in this fixed order:
1. Participant `custom_prompt` (existing).
2. Spec 021 register-slider delta (when 021 ships; absent for now).
3. Conclude delta (this spec; injected only during conclude phase).

`src/prompts/tiers.py` exposes a deterministic ordered Tier 4 hook (`tier4_extras: list[Tier4Fragment]`) where each fragment is appended in the documented order. Spec 025 ships the `ConcludeDelta` fragment + the registry shape; spec 021 lands its `RegisterDelta` fragment in the slot already reserved.

**Rationale**: spec 021 has not shipped. Locking the ordering now prevents a later amendment to spec 025 when 021 lands. Additive ordering is the cleanest semantic ("each fragment adds context the AI sees in order") and survives both specs landing in either sequence. The user's clarify pass deferred this question explicitly, but a forward-compatible decision can be locked at plan time without committing to either of the deferred answers being "wrong."

**Alternatives considered**:
- **Wait for spec 021 to land first** — defers spec 025 indefinitely. Rejected.
- **Conclude delta replaces participant tier text** — rejected by FR-009 explicitly ("MUST NOT replace tier text or custom_prompt").
- **Operator-tunable ordering via env var** — adds config surface for a near-zero-value choice. Rejected.

---

## §5 — Conclude delta exact text

**Decision**: hardcoded text in `src/prompts/conclude_delta.py`:

> The session is approaching its conclusion. In your next turn, please summarize your position so far and offer a final conclusion. The orchestrator will pause the loop after every active participant has had a turn to wrap up.

**Token budget**: ~45 tokens (Claude tokenizer estimate). Well below any participant's tier-4 token slack.

**Rationale**: two sentences cover both the immediate ask (summarize + conclude) and the orchestrator behavior (pause-after) so the AI can pace its conclusion. Plain English satisfies §4.13's human-readable requirement (conclude delta is part of inter-AI content path, not metadata). Avoids:
- Imperative "MUST" language that would feel out-of-register against tier 1-3 system prompts.
- Time/turn references that would require the conclude delta to be parameterized per-session.
- Provider-specific phrasing that might land worse on one model than another.

**Alternatives considered**:
- **Single-sentence "Wrap up your position now"** — cheaper but loses the orchestrator-behavior context, which the spec rationale flags as load-bearing for the AI's pacing.
- **Three-sentence variant adding "The summary will be archived for the session record"** — adds factual info but doesn't change AI behavior; trims to two sentences.
- **Operator-tunable conclude delta via config file** — future feature (per spec line 853–855). v1 ships hardcoded; tunable can land later without amendment.

---

## §6 — Spec 011 amendment scope

**Decision**: bundled into this spec's branch. `specs/011-web-ui/spec.md` was amended on 2026-05-07 with a `### Session 2026-05-07 (spec 025 length-cap amendment)` Clarifications entry, US13 (Session-Length Cap Configuration and Conclude-Phase Banner), four new FRs (FR-021..FR-024) marked "Phase 3, ships with spec 025", SC-007 (Phase 3 e2e contract), and a new "Phase 3a — Length-cap UI (ships with spec 025)" subsection in Implementation Phases.

**Four UI pieces wired into spec 011**:
1. **FR-021 — Cap-config control set in session-create modal** — preset selector (Short/Medium/Long/Custom) + custom-value inputs for time + turns when Custom selected. Posts to session-create.
2. **FR-022 — Cap-config control set in session-settings panel** — same control surface as session-create, plus current-elapsed display so the facilitator sees what they're setting against. Posts to the cap-set endpoint per [contracts/cap-set-endpoint.md](./contracts/cap-set-endpoint.md). Gated by spec 011 FR-009 facilitator-only role check.
3. **FR-023 — Conclude-phase banner with countdown** — banner at the top of the participant view, driven by [`session_concluding`](./contracts/ws-events.md) WS event payload. Hides on `session_concluded` or `loop_state_changed → running` (FR-013 cap-extension exit).
4. **FR-024 — Disambiguation modal** — modal triggered by 409 from the cap-set endpoint, presenting the two interpretation options (absolute / relative) with the consequence text from §3 above. SPA re-POSTs with explicit `interpretation`.

**Rationale (post-decision)**: bundling keeps the SPA contract change in lockstep with the backend WS event emitters and cap-set endpoint, so PR review can verify end-to-end behavior. Phase 2's "Implemented" status on spec 011 is preserved; the four new FRs are explicitly labelled "Phase 3, ships with spec 025" so the implementation gate is clear.

**Alternatives considered**:
- **Separate `fix/spec-011-cap-banner` PR after contracts lock** — was the default in the first draft of this research note. User chose bundling 2026-05-07 ("fix spec 11").
- **Defer spec 011 amendment until this spec is Implemented** — leaves the SPA without a contract for 4 UI pieces while the backend ships them as WS events nobody renders. Rejected.

---

## §7 — Cap-decrease detection placement

**Decision**: service-layer helper `length_cap.detect_decrease_intent(session, submitted)` in `src/orchestrator/length_cap.py`. The HTTP endpoint, the MCP tool variant, and any future transport call this helper to obtain either a clean `CapUpdatePlan` or a `DisambiguationRequired` object. The transport layer translates `DisambiguationRequired` into the appropriate response shape (HTTP 409 / MCP error variant).

**Rationale**: keeps the rule reusable across transports (HTTP via session-controls, MCP via mcp_server tools, any Phase 4+ transport). Single source of truth for "is this a decrease?" + "what are the two interpretations?" prevents drift between HTTP and MCP behavior. Endpoint code becomes a thin translator.

**Alternatives considered**:
- **Inline in HTTP endpoint** — duplicates logic in the MCP tool. Rejected.
- **Database trigger / constraint** — wrong layer for behavioral semantics; constraint should reject genuinely invalid values (FR-021), not arbitrate user intent. Rejected.

---

## Summary of Resolutions

| # | Question | Decision |
|---|---|---|
| 1 | Accumulator persistence | Durable column `sessions.active_seconds_accumulator` |
| 2 | Endpoint shape | Extend existing session-settings endpoint |
| 3 | Disambiguation transport | 409 + idempotent re-POST with `interpretation` field |
| 4 | Tier 4 composition with 021 | Forward-compatible ordered hook |
| 5 | Conclude delta text | Two-sentence hardcoded English (~45 tokens) |
| 6 | Spec 011 amendment | Separate docs PR after contracts lock |
| 7 | Decrease detection placement | Service-layer helper in `length_cap.py` |

All Phase 0 unknowns resolved. Phase 1 design docs (data-model.md, contracts/, quickstart.md) can proceed.
