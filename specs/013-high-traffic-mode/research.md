# Phase 0 Research: High-Traffic Session Mode

Resolves the six NEEDS CLARIFICATION items raised in `plan.md`. Each section follows the Decision / Rationale / Alternatives format.

## 1. Audit-event storage shape

**Decision**: Reuse the existing `admin_audit_log` table for the three new event types (`observer_downgrade`, `observer_restore`, `observer_downgrade_suppressed`). No schema changes. Payload metadata (which threshold tripped, observed-vs-configured values) packs into the existing `previous_value` / `new_value` text columns as JSON.

**Rationale**:
- `admin_audit_log` columns are `(session_id, facilitator_id, action, target_id, previous_value, new_value, timestamp)`. `action` is free-form text — adding new action strings is purely additive (validated by inspection of [tests/conftest.py:302](../../tests/conftest.py)).
- Session-id-as-denormalized-identifier (no FK) means audit rows survive participant deletion, matching the 001 §FR-019 retention pattern that already covers admin actions.
- Per-event-type tables would force a schema migration AND a new repository class for ~20 lines of payload structure that JSON-in-text already serves.
- For the Suppressed variant (last-human-protection), the `restore_at_or_null` field cleanly maps to leaving `new_value` null.

**Alternatives considered**:
- New `observer_downgrade_log` table — rejected. Schema cost outweighs query benefit; the existing log is queried by `action` already.
- Add a typed `metadata JSONB` column to `admin_audit_log` — rejected as out of scope (would be a beneficial future cleanup but isn't FR-required for this feature; opens a multi-spec migration discussion).

**Audit-row shape** (what each new action writes):
- `action='observer_downgrade'` — `target_id=<participant_id>`, `previous_value=<role pre-downgrade JSON>`, `new_value=<reason JSON: {threshold, observed, configured}>`.
- `action='observer_restore'` — `target_id=<participant_id>`, `previous_value=<observer>`, `new_value=<role JSON post-restore>`.
- `action='observer_downgrade_suppressed'` — `target_id=<participant_id>`, `previous_value=<would-have-downgraded role>`, `new_value=<reason JSON: last-human protection>`.

`facilitator_id` is set to the session's facilitator (the orchestrator acts on the facilitator's behalf for these decisions, mirroring how circuit-breaker pause/resume already attributes itself).

## 2. `SACP_OBSERVER_DOWNGRADE_THRESHOLDS` parse format

**Decision**: Comma-separated `key:value` string per the spec proposal — `participants:4,tpm:30,restore_window_s:120`. Keys are required; values are integers. Unknown keys cause startup exit (V16 fail-closed). Optional `restore_window_s` defaults to 120s if unset within the composite.

**Rationale**:
- Single env var keeps deploy ergonomics simple — operators set one var to enable the mechanism, and it carries all three knobs together.
- The `key:value` format is human-readable, grep-able, and immune to JSON-quoting hell in `.env` files / Compose files / k8s ConfigMaps.
- `restore_window_s` joins the same composite because the three keys are functionally coupled (tuning one without the others produces inconsistent behavior).

**Validator behavior**:
- Empty/unset → `None` (mechanism disabled, fail-closed).
- Set-but-unparseable (no colons, malformed key=value) → startup exit with the offending raw value in the error.
- Required keys missing (`participants` OR `tpm`) → startup exit naming the missing key.
- Out-of-range value (e.g., `participants:1` or `tpm:0`) → startup exit naming the offending key+value.
- Unknown keys (e.g., `participants:4,foo:bar`) → startup exit naming the unknown key.

**Alternatives considered**:
- Three separate env vars (`SACP_OBSERVER_DOWNGRADE_PARTICIPANTS`, `_TPM`, `_RESTORE_WINDOW_S`) — rejected. Operators could set one without the others, producing partially-valid config. Single-var approach forces atomic enable/disable semantics.
- JSON env var — rejected. Quoting headaches in shell/.env contexts; the parse format saves no expressiveness for three integer keys.

## 3. "Lowest-priority active participant" heuristic

**Decision**: Composite priority key, lower wins downgrade:
1. `status != 'paused'` — paused participants are excluded entirely; they're already not active.
2. `model_tier` rank: `low < mid < high < max` (lowest tier downgrades first).
3. `consecutive_timeouts` (desc) — within a tier, the participant with the most recent timeouts goes first.
4. `last_seen` (desc) — within a (tier, timeouts) tie, the participant who's been quiet longest goes first.
5. Stable tie-break: `id` ascending (deterministic).

**Rationale**:
- All four signals already live on the `Participant` model — no new fields needed.
- `model_tier` is the operator's stated priority — keeping the highest tier active during a traffic spike preserves session quality.
- `consecutive_timeouts` reflects current health; participants already wobbling are the right candidates to remove load from.
- `last_seen` is a recency tie-breaker — favors keeping the active conversation flow with the participants who are actually engaged.
- Determinism via id-asc means tests can assert a specific downgrade target without flake.

**Alternatives considered**:
- Pure `model_tier` ordering — too coarse; ties are common in 5-participant Phase 3 sessions.
- Cost-based (lowest cost-per-token first) — rejected; cost is operator-economic, not a quality signal. Operator who picked an expensive model wants it to stay active.
- Random selection — rejected; non-deterministic, untestable, surprising to operators.

## 4. Batching transport granularity

**Decision**: Per-session flush task, single in-process queue keyed by `(session_id, recipient_id)`. The flush task wakes on cadence tick, drains all queues for that session in one pass, emits one websocket event per recipient via the existing `broadcast_to_session` path (extended with a "batch envelope" event type).

**Rationale**:
- Per-session task gives one cadence clock per session, matching operator mental model — "this session is in batched mode, here's its cadence". Per-recipient tasks would multiply scheduler overhead without benefit.
- One event per recipient (not one event per source turn) is what FR-002 requires ("all AI messages produced since the previous delivery, in original turn order").
- Hooks into existing `broadcast_to_session` — no new connection management. Batch-envelope events are additive in [src/web_ui/events.py](../../src/web_ui/events.py).
- The Web UI receives the envelope and unwraps it to display turns sequentially; renderer side-effect is minimal (existing message-event handler, called N times).

**Alternatives considered**:
- Per-recipient flush task — rejected. Multiplies asyncio task count by recipient count; offers no behavioral difference since recipients in the same session share a clock by design.
- Server-sent batched delivery via SSE — rejected; existing transport is WebSocket, no reason to fork.
- Client-side batching (just always send per-turn, let UI batch) — rejected; doesn't satisfy FR-001 (orchestrator MUST coalesce). Also pushes complexity into the renderer for a queue-management problem better solved server-side.

**Bypass rule for state-change events** (FR-004): convergence declarations, session-state transitions, security events — none flow through the batch envelope. They route through their existing per-event broadcast paths immediately, so a session reaching convergence during a batch window doesn't see its convergence message stuck behind a queue.

## 5. Convergence-override resolution timing

**Decision**: Pass the override into `ConvergenceEngine.__init__` via the existing `threshold` parameter; resolve it once at session-start in the loop's session-init path. No refactor needed.

**Rationale**:
- Inspection of [src/orchestrator/convergence.py:33-44](../../src/orchestrator/convergence.py) confirms the engine already takes `threshold: float = DEFAULT_THRESHOLD` as a constructor arg. The session-start path can read `HighTrafficSessionConfig.convergence_threshold_override` and pass either it or the global default.
- This satisfies SC-003's constant-time-read requirement: once the engine is constructed, `self._threshold` is a field access, no env-var lookup per turn.
- Spec assumption (line 472–474) anticipated needing a refactor — confirmed unnecessary.

**Alternatives considered**:
- Inject a callable that returns the threshold — over-engineered; the threshold doesn't change mid-session, and the spec explicitly requires resolution at session-start.
- Subclass the engine for high-traffic sessions — rejected; adds inheritance with no behavioral difference beyond a single constructor arg.

## 6. Phase 2 regression contract enforcement (SC-005)

**Decision**: Structurally enforce "additive when unset" via a single conditional at each integration site:

```python
if session.high_traffic_config is None:
    # exact Phase 2 code path
else:
    # high-traffic branch
```

Backed by a regression test file (`tests/test_013_regression_phase2.py`) that runs a curated set of Phase 2 acceptance scenarios with all three env vars unset, asserting identical behavior (same dispatch decisions, same routing-log entries, same WebSocket events).

**Rationale**:
- Single conditional read at each call site makes the additive guarantee mechanically obvious — code review can see the Phase-2-preserving branch unchanged.
- `HighTrafficSessionConfig` resolves to `None` when ALL three env vars are unset (or when ANY env var is invalid AND the operator wants fail-closed semantics — but invalid here means startup exit per V16, so runtime never sees a partial config).
- A small curated regression file (5–8 high-value Phase 2 scenarios) catches the leak case without re-running the full Phase 2 suite — the existing test suite already covers Phase 2 behavior; this file specifically asserts "still works in the high-traffic-mode-disabled state".

**Curated Phase 2 scenarios for the regression test**:
1. Single-AI / single-human turn loop completes with no batch envelope emitted.
2. Multi-AI session reaches convergence using the global threshold (no override).
3. Circuit breaker pauses a participant on consecutive timeouts (no observer-downgrade interference).
4. Review-gate UI receives per-turn drafts (not batched).
5. Session-state-change events broadcast immediately (no envelope wrapping).
6. Routing log shape is unchanged (no new stage rows for downgrade-evaluation).

**Alternatives considered**:
- Run the entire Phase 2 test suite under both unset-env and set-env configurations — rejected; doubling CI cost for a property already enforceable structurally.
- Property-based test that generates random Phase 2 inputs and asserts equivalence — rejected per Constitution residuals (Hypothesis dep weight not justified for this case).
