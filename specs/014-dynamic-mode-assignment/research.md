# Phase 0 Research: Dynamic Mode Assignment

Resolves the seven NEEDS CLARIFICATION items from `plan.md`.

## 1. Density-anomaly algorithm

**Decision**: Reuse the existing per-turn density-anomaly flag from [src/orchestrator/density.py](../../src/orchestrator/density.py) as the raw signal. The controller's "density-anomaly rate" signal source is the count of flagged turns in the rolling 5-minute observation window, divided by the window length in minutes (rate = flagged_turns_per_minute).

**Rationale**:
- The existing density module already produces an authoritative anomaly flag emitted to `convergence_log` with `tier='density_anomaly'` (per the spec-004 amendment that landed). Reusing that flag avoids duplicating measurement code and keeps a single source of truth.
- Counting flag events per window is the simplest interpretation of "density anomaly rate" and discriminates the technical-review use case (§5) — attention-area shifts produce bursts of flagged turns concentrated in time, distinguishable from steady-state low-flag-rate periods.
- A higher-cardinality "shifts per window" derivative would require new topic-embedding shift detection — significant new ML work for marginal accuracy gain. Defer that to a future amendment if operator feedback shows the simple count is too noisy.

**Alternatives considered**:
- New topic-embedding-shift detector — rejected for now. Re-uses the density signal effectively, no new ML model required.
- Boolean "anomaly currently present" — rejected. Loses temporal information that the rate captures cleanly.

## 2. Spec 004 similarity-score exposure

**Decision**: Add a `last_similarity` property on `ConvergenceEngine` that returns the most-recently-computed similarity value (computed during `evaluate_convergence` per turn — see [src/orchestrator/convergence.py:177](../../src/orchestrator/convergence.py)). The DMA controller reads this property at each decision cycle and computes the per-window derivative on its own buffer. No DB reads from `convergence_log` on the hot path.

**Rationale**:
- The engine already computes similarity per turn; exposing it as a read-only property is a one-line change with no behavior impact.
- Computing the derivative on the controller side keeps spec 004 ignorant of spec 014 (clean dependency direction — 014 → 013 → 004, never reversed).
- Avoiding `convergence_log` reads on the hot path matches V14 — no per-cycle DB cost.

**Alternatives considered**:
- Callback hook — rejected. Pushes spec-004 into a publish-subscribe pattern for one consumer; awkward for a per-turn signal that the controller polls.
- Spec 004 amendment to compute and store derivatives itself — rejected. That couples the engines and forces 004 to know about controller-window semantics it shouldn't have to.

**Hook contract** (minimal):
```python
class ConvergenceEngine:
    @property
    def last_similarity(self) -> float | None:
        """Most recent similarity score, or None if no turn has been evaluated yet."""
        return self._last_similarity
```

Internal field `_last_similarity` is set inside `evaluate_convergence` at the same point where `similarity_score=similarity` is logged (line 177). Single-point change.

## 3. Controller task lifecycle

**Decision**: One asyncio task per session, spawned in `loop.py`'s session-init path immediately after the `HighTrafficSessionConfig` resolves and `ConvergenceEngine` is constructed. Task is cancelled in the session-teardown path. Task does not block session shutdown — cancellation is best-effort; any in-flight decision cycle completes or is dropped.

**Rationale**:
- Phase 3 ceiling is small (5 sessions × 5 participants typical). Per-session task is ~minimal asyncio overhead at this scale.
- Per-session lifecycle matches the controller's data lifecycle (signals are session-scoped) and keeps the implementation simple — no shared state across sessions, no cross-session locking.
- Centralized polling loop would force a single rate budget across all sessions, making per-session decision-cap semantics (FR-002) harder to express.

**Lifecycle integration points**:
- Session start: `dma_controller.start(session_id, config, signals_provider)` returns the task handle stored on the session's runtime context.
- Session teardown: `dma_controller.stop()` cancels the task; any pending audit writes flush before cancellation completes.
- Restart: spec 014 line 261 says state is session-local and not persisted; the task starts fresh on session restart with an empty ring buffer.

**Alternatives considered**:
- Centralized polling loop — rejected per above; per-session task model is simpler and matches Phase 3 scale.
- Run the controller inline in the turn-loop — rejected. Couples decision-cycle cadence to turn cadence; FR-002 wants a fixed time-based cap, not a per-turn dependency.

## 4. Auto-apply mutation safety on `HighTrafficSessionConfig`

**Decision**: Extend `HighTrafficSessionConfig` (spec 013) with controller-only mutator methods `engage_mechanism(name: Literal["batching", "convergence_override", "observer_downgrade"])` and `disengage_mechanism(name)`. Methods set per-mechanism active flags; mechanism call-sites in 013 check both `(config is not None) AND mechanism.is_active(name)`. Default state on session-start is "all active when their env vars are set" — same as spec-013 baseline. The DMA controller mutates active flags; no env var values are ever touched.

**Rationale**:
- Preserves spec-013's "additive when env var unset" guarantee — if `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S` is unset, batching is structurally disabled regardless of the active flag (the call-site short-circuits before reading the flag).
- Auto-apply toggles only affect mechanisms whose env vars ARE set. This matches spec 014's edge-case rule: when auto-apply ENGAGE coincides with absent env vars, the mechanism is skipped silently and the audit row records `skipped_mechanisms[]`.
- Spec 013's frozen-config semantics hold for all fields except the active flags. The flags are explicitly mutable in the controller's path; everywhere else they're read-only.

**Mutation invariants** (enforced in tests):
- `engage_mechanism(name)` requires the mechanism's env var to be set; calling it on an unconfigured mechanism is a no-op (returns False; logged but not audited as a transition).
- `disengage_mechanism(name)` is always allowed but is a no-op if the mechanism is already inactive.
- All mutations emit `mode_transition` audit rows via the controller (the config object itself does NOT emit audit events — separation of concerns).

**Alternatives considered**:
- Make `HighTrafficSessionConfig` fully immutable; force the controller to construct a new config and swap it atomically — rejected. Race-prone at the spec-013 mechanism call-site (which would need to capture the config reference before evaluation).
- Move mechanism-active state out of the config into a separate `MechanismActivationState` object — rejected as over-engineering for three boolean flags.

## 5. Decision-cycle throttle implementation

**Decision**: Token-bucket rate limiter with refill at 12 tokens/minute (one token / 5 seconds). Each decision cycle consumes one token; cycles attempted while empty drop and emit `decision_cycle_throttled` (rate-limited per FR-013 to once per dwell window). Bucket capacity = 1 (no burst — strict cap, not amortized).

**Rationale**:
- Token bucket cleanly expresses "12/min cap, drop on overflow" with constant-time check per cycle.
- Capacity-1 bucket means the controller cannot save up tokens during quiet periods and burst — matches FR-002's "rate not exceeding the cap" exactly.
- 5-second refill matches the spec's "one decision every 5 seconds" intuition (line 279 of spec).

**Implementation sketch**:
```python
class DecisionCycleBudget:
    def __init__(self, cap_per_minute: int = 12):
        self._refill_interval_s = 60.0 / cap_per_minute
        self._next_eligible_at = time.monotonic()

    def try_acquire(self) -> bool:
        now = time.monotonic()
        if now < self._next_eligible_at:
            return False
        self._next_eligible_at = now + self._refill_interval_s
        return True
```

**Alternatives considered**:
- Wall-clock interval check (acquire only if `now > last_cycle + interval`) — equivalent to capacity-1 token bucket; this IS that, just named differently. Use the simpler form.
- Generic token-bucket library — rejected. ~6 lines of code; no dependency.

## 6. Recommendation deduplication

**Decision**: Emit `mode_recommendation` only when the action changes (NORMAL→ENGAGE or ENGAGE→DISENGAGE), not on observed-value changes within the same action. The controller stores the last-emitted action per session and compares the current cycle's decision against it.

**Rationale**:
- Spec FR-005 phrasing "decision differs from most-recently-emitted recommendation" supports either interpretation; the action-change reading produces a sane operator audit log (one row per state change rather than one row per cycle).
- Operators care about state changes, not telemetry — telemetry per cycle is what `routing_log` per-stage timing is for (spec 003 §FR-030).
- The trigger signal value at the moment of state change is captured in the audit row's payload; subsequent cycles with different observed values but the same action contribute nothing new.

**What's still emitted on every cycle**:
- The `triggers[]` array in `ControllerState` is updated every cycle (in-memory only).
- Per-cycle `routing_log` timing rows fire every cycle (V14 instrumentation).
- `decision_cycle_throttled` and `signal_source_unavailable` events fire on their own conditions (rate-limited per FR-013).

**Alternatives considered**:
- Emit on every cycle — rejected. Floods audit log; operators can't tell ENGAGE-just-happened from ENGAGE-still-happening without manual diff.
- Emit on threshold-margin change (e.g., observed value crosses 1.5× threshold) — rejected. Adds complexity for marginal operator value.

## 7. Topology-7 future-proofing

**Decision**: At controller startup (`dma_controller.start`), read `SACP_TOPOLOGY` env var. If set to `7`, do not spawn the controller task and do not register signal sources. Skip silently with a one-time INFO log. No `SACP_DMA_*` env-var validation happens in topology-7 mode (the validators run unconditionally per V16, but the controller-init path is the gating point).

**Rationale**:
- V12 says the spec is incompatible with topology 7. The controller MUST disable itself; "must" needs an enforcement point.
- An explicit env-var gate makes the topology-mismatch case observable in startup logs without forcing operators to remove `SACP_DMA_*` configuration if they're transitioning between topologies.
- One-time INFO log avoids alert fatigue while remaining grep-able.

**SACP_TOPOLOGY env var status**: This var doesn't exist today. Adding it as a topology selector is out of scope for this spec — the gate-check is *aspirational* until topology 7 ships and a topology-selection mechanism exists. For now, the controller's topology check is "always topology 1–6 because topology 7 isn't deployable yet" and the gate is dead code in Phase 3.

**Alternatives considered**:
- Detect topology dynamically (e.g., from MCP-to-MCP connection state) — rejected. Topology 7 doesn't exist yet; future deployment will surface its own detection mechanism.
- No gate; let the controller fail at runtime — rejected. Violates V12's "silent assumption = incomplete" rule.

**Documentation note**: This decision adds a forward reference in `quickstart.md` ("If/when topology 7 ships, set `SACP_TOPOLOGY=7` to disable this controller") so the gate is discoverable when relevant.
