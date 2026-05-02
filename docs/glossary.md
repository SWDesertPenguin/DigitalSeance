# SACP Glossary

Single source of truth for project terminology. Every term is defined once here; specs and other docs cross-reference rather than redefine.

Terms are alphabetized within each category. New entries land in the PR that introduces the concept, not retroactively.

---

## A

### Adversarial rotation

Periodic detector-regression run that re-points sanitizer / exfiltration / jailbreak detectors at a curated adversarial corpus to confirm zero regressions before merging detector changes.

### Advisory lock

PostgreSQL `pg_advisory_lock` acquired per-session by the turn loop so at most one orchestrator process drives turn execution for a given session. Phase 1's single-instance deployment makes contention rare; multi-instance deployments race on the lock and are explicitly out of scope until Phase 3. Wait duration is captured into `routing_log.advisory_lock_wait_ms`.

### Append-only

Operational log tables (routing_log, usage_log, convergence_log, admin_audit_log, security_events) accept INSERTs only — no UPDATE / DELETE methods exist on the log repository. Enforced at the repository interface layer.

## B

### Breaker (closed / open)

Per-participant circuit breaker. `closed` = healthy and dispatched normally; `open` = recent consecutive failures crossed the threshold and the loop skips this participant until the breaker resets. Distinct from session lifecycle states.

## C

### Cadence preset

Per-session knob controlling post-turn delay shape: `sprint` (no delay), `cruise` (default — convergence-driven slowdown), `idle` (longest delay).

### Canary leakage

Detection event when a known canary token (planted via the canary machinery) appears in an AI response — strong signal of a data-exfiltration attempt. Flagged by the exfiltration layer; routed to `security_events` with `layer="exfiltration"` and `findings` listing the canary id.

### Complexity classifier

Per-turn input scorer that picks `low` / `mid` / `high` / `max` based on prompt content. Drives tier delta selection via `prompt_tier` and budget allocation via `min_model_tier`.

### Convergence

Phenomenon where multiple AI participants converge on the same answer or phrasing across turns, signalling lost diversity. Measured as cosine similarity over rolling-window message embeddings. Sustained high similarity triggers a divergence prompt.

### Cruise

Default `cadence_preset` value. Compute the post-turn delay from the current convergence score: low similarity = short delay, high similarity = longer delay. See also: sprint, idle.

## D

### Datamarking

Inserting a unique watermark into AI-routed prompts so leakage of the watermark in any downstream channel is recoverable evidence.

### Divergence prompt

Facilitator-attributed system message injected into the next turn's context when convergence crosses threshold.

## F

### Fail-closed

A layer that, when uncertain or when its own machinery breaks, denies the operation rather than allowing it. Examples: security-pipeline regex crashes skip the turn; env-var validation failures exit before port-bind.

### Facilitator

The privileged session role: creates sessions, approves pending participants, sets budgets, can force routing flips, and is the only role allowed to override review-gate drafts.

### Fire-and-forget summarization

Summarization checkpoints run in a background task and never block the turn loop. On failure the loop logs `Summarization failed` and continues — the missed summary is recovered on the next checkpoint boundary.

## H

### Held draft

Review-gate draft whose `status='pending'` — staged but not yet approved / rejected / edited. While drafts are held, the loop pauses dispatch for that participant (or session, depending on `review_gate_pause_scope`).

## I

### Idle

Slowest `cadence_preset`. Used for low-bandwidth deliberation modes.

### Interrupt

Facilitator-injected message that takes priority on the next turn's context window. Persists to `interrupt_queue`; consumed at the start of the target participant's next turn and marked delivered.

## M

### MVC floor

Minimum Viable Context — the smallest context that reliably produces a useful AI response. The floor is set at 3 turns; `SACP_CONTEXT_MAX_TURNS` enforces this bound.

## N

### Narrative-only fallback

Summarizer fallback that emits a plain-prose narrative summary when the structured-summary path fails (provider error, timeout, malformed JSON). Keeps summary continuity rather than dropping a checkpoint.

## O

### Observer

Routing preference that excludes a participant from dispatch but keeps them present in the session for read-only purposes. Set via `routing_preference='observer'`; revertible by the facilitator.

### Override path

Facilitator-only flow that bypasses a held review-gate draft. The secure-by-design implementation governs this path's audit and re-validation semantics.

## P

### Pattern-list update workflow

The four-step process by which new attack patterns join the sanitizer / exfiltration / jailbreak detector lists: incident → single-PR pull (corpus + regression test + pattern + runbook update) → zero-regression check on broader corpus → land within one cycle.

### Pending / active / paused / removed

Participant lifecycle states:
- `pending`: invited but not yet approved by facilitator
- `active`: approved and eligible for dispatch
- `paused`: approved but excluded from dispatch (manual or breaker-driven)
- `removed`: rejected — row hard-deleted, audit log retained

## R

### Request-id propagation

Per-request UUID generated at ingress and threaded through downstream logs so a single user action can be traced across orchestrator, provider-bridge, and persistence layers. Implementation deferred.

### Review gate

Mechanism that intercepts an AI's draft response before it enters the transcript, surfacing it to the facilitator for approve / edit / reject. Held drafts pause the loop within their pause scope.

### Route-and-assemble-and-dispatch-and-persist

Canonical four-stage turn-loop pipeline. The stage names also key the `routing_log` per-stage timing columns (`route_ms`, `assemble_ms`, `dispatch_ms`, `persist_ms`).

## S

### Secure-by-design

Defenses must apply on every authoritative path, including operator overrides.

### Sponsored AI

AI participant where a human user provides the API credentials and pays for token usage on the AI's behalf. Distinct from observer — sponsored AIs participate fully; the sponsor relation is captured via `participants.invited_by`.

### Spotlighting

Defensive marker pattern (`<<USER_INPUT>> ... <</USER_INPUT>>`) wrapped around any user-controlled text that is later concatenated into a system prompt, so the model can recognize trust boundaries in its context.

### Sprint

Fastest `cadence_preset`. Used for high-bandwidth back-and-forth modes. See also: cruise, idle.

## T

### Tier delta

Provider-specific 4-tier (low / mid / high / max) prompt content delta — lower tiers ship a smaller system prompt to save tokens; higher tiers ship the full delta for capability ceiling. Selected per turn from `participants.prompt_tier` × `participants.model_tier`.

---

This glossary is the floor, not the ceiling — add an entry whenever a spec, ADR, or code comment reaches for a term that isn't defined here.
