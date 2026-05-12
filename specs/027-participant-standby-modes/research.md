# Research: AI Participant Standby Modes

**Spec**: `specs/027-participant-standby-modes/spec.md`

This document captures the design-research surface that informed the eight Session 2026-05-12 clarifications and the four implementation phases in `plan.md`.

## §1 — Status enum extension vs. virtual sub-state vs. dedicated boolean

**Decision**: Extend the existing `participants.status` enum with one new value `standby`.

**Considered alternatives**:

1. **Virtual sub-state on the existing `paused` value** (e.g., distinguish manual-paused from gate-blocked via a side flag). Rejected because the round-robin skip-set arithmetic already discriminates on `status='active'` vs. everything else; introducing a sub-state means every skip-eligible check has to know about the sub-distinction, blast-radius across `loop.py`, `router.py`, and every WS-event emitter is high.
2. **Dedicated boolean column `is_standby BOOLEAN`** with `status` left alone. Rejected because two participants in different statuses but both with `is_standby=true` would need separate dispatch paths — e.g., a `circuit_open` participant who also has an unresolved gate. The Session 2026-05-12 Q1+Q4 resolutions specify precedence (`paused > standby > active`, `circuit_open > standby`), which is most naturally expressed as a single enum.
3. **Status enum extension** (chosen). Single source of truth, clear precedence relations, minimal blast radius — the round-robin skip-set already enumerates the non-`active` statuses.

The new value docks at the same enum layer as `pending`, `paused`, `removed`, `circuit_open`. The migration adds the CHECK constraint `status IN ('active','pending','paused','removed','circuit_open','standby')`. Pre-existing rows are unaffected.

## §2 — Detection signal vocabulary coordination with spec 014

**Decision**: Consume spec 021's filler-scorer aggregate output (the canonical "filler heuristic" surface that already shipped). The coordination with spec 014 (called out in the user's brief) is satisfied by NOT double-firing when spec 014's `density_anomaly` signal would trip for the same participant on the same tick.

**Background**: The user's brief uses the phrase "spec 014's off-rails signal." Spec 014 (implemented 2026-05-08) does not actually use the phrase "off-rails" — it ships four signals (turn_rate, convergence_derivative, queue_depth, density_anomaly) for the dynamic-mode-assignment controller. The closest semantic match to the user's intent is `density_anomaly`, which fires on attention-area shifts that look like a session going off-rails. But the canonical "filler heuristic" lives in spec 021's `compute_filler_score` (which the user's brief itself cross-references). So the resolution per Session 2026-05-12 Q2:

- Detection signal #4 reads `routing_log.filler_score` for the participant's last 2 turns. Both must exceed `SACP_FILLER_THRESHOLD` (or the per-family default).
- The standby evaluator skips signal #4 for the current tick when a `density_anomaly` `routing_log` row exists for the same participant + same tick — this is the "off-rails-vocabulary coordination" with spec 014.

The two signals trip on overlapping but not identical patterns. Filler-scorer catches "the AI keeps saying the same hedge"; density_anomaly catches "the session is shifting attention without converging." Either one is a valid standby trigger; double-firing on the same tick would double-write the audit row.

## §3 — Pivot-cycle counter durability

**Decision**: Persist the consecutive-standby-cycles counter on `participants.standby_cycle_count` (new column). Volatile in-memory would lose state on loop restart — exactly the case where the pivot is most useful.

**Considered alternatives**:

1. **In-memory dict keyed by participant_id** in the loop process. Rejected because the loop restarts on deployment, on crash, on planned maintenance. A multi-hour human absence (the pivot's target case) is precisely the scenario where the loop is most likely to restart during the absence — losing the cycle count would prevent the pivot from ever firing across a restart.
2. **Compute on demand from `routing_log` rows** (count consecutive `skipped_standby` reasons). Rejected because the loop's per-tick standby evaluator would run an O(N) scan over routing_log every tick — violates the V14 O(1) budget.
3. **Durable column on `participants`** (chosen). One UPDATE per standby-tick, one UPDATE per standby-exit (reset to 0). The participants table is small (typical session has < 10 participants); the UPDATE is index-tight.

The accumulator is reset on every standby-exit transition (not just successful gate-clear — also on `paused` supersedence, on `circuit_open` precedence, on participant departure).

## §4 — Pivot message persistence shape

**Decision**: `speaker_type='system'` + `metadata->>'kind' = 'orchestrator_pivot'` JSONB key. No new column, no new speaker_type.

**Considered alternatives**:

1. **New speaker_type `'pivot'`**. Rejected because the security pipeline, summarizer, and UI all switch on speaker_type — introducing a new value forces churn at every check site. Trust-tier is the same as `system` (system-trust, hardcoded, pre-validated); the distinction is rendering, not security.
2. **New column `messages.message_kind`**. Rejected because the discriminator is needed only by the summarizer + UI rendering path; widening the schema for two consumers is excessive. JSONB metadata is the existing extension surface (spec 001 already documents `messages.metadata`).
3. **Metadata JSONB key** (chosen). Reads in spec 005 + spec 011 are constant-time (`metadata->>'kind' = 'orchestrator_pivot'`); writes are one INSERT during pivot injection. Forward-compatible if other system-message kinds emerge.

## §5 — Tier 4 delta composition order

**Decision**: Fixed additive order — spec 021 register-slider first, spec 025 conclude delta second, spec 027 wait-acknowledgment third.

The order mirrors the order each delta SHIPPED in (021 implemented 2026-05-07, 025 implemented 2026-05-09, 027 implemented 2026-05-12). The composition happens in `src/prompts/tiers.py:assemble_prompt`; the call signature gains a new keyword arg `standby_ack_delta` appended after `conclude_delta` in the assembly chain.

Operator-configurable order was considered and rejected per Session 2026-05-12 Q5 — operators reordering deltas could land in tested-but-illegal compositions (e.g., conclude delta BEFORE register slider would mean the model sees the concluding directive before knowing the session's register, which inverts the intended ordering).

## §6 — Standby-paused / standby-circuit_open precedence

**Decision**:

- `circuit_open` > `standby` (FR-013). A participant whose provider is failing does not undergo standby evaluation — the failure is a higher-priority signal.
- `paused` > `standby` (FR-012). A facilitator-issued manual pause supersedes auto-standby. On resume, standby re-evaluates.
- `standby` > `observer_downgrade` (FR-026). Gate-blocked outranks traffic-shape per Session 2026-05-12 Q1.

The precedence chain is encoded as a totally-ordered comparison in the standby evaluator: `if participant.status in {'circuit_open', 'paused'}: skip_standby_eval`. The observer-downgrade evaluator gains a corresponding skip: `if participant.status == 'standby': skip_downgrade_eval`.

## §7 — Detection signal #3 thresholds (stance similarity + token count)

**Decision**: Hardcoded in v1 — `cosine_similarity > 0.8` AND `new_token_count < 50` against the immediately prior turn.

The 0.8 threshold borrows spec 004 §FR-014 convergence semantics; the 50-token threshold borrows spec 004 §FR-016 short-output handling. Both values are tested in `tests/test_027_standby_evaluator.py` against fixture turns that span the threshold boundaries.

The two-condition AND (vs. either-OR) per Session 2026-05-12 Q8 — either-OR fires too aggressively (every short-but-novel turn would flag); two-condition AND requires both repetition AND low-content for the signal to trip.

The sentence-transformers pipeline reused for similarity is the same `all-MiniLM-L6-v2` SafeTensors model spec 004 already loads — no new model dependency.

## §8 — V14 budget instrumentation strategy

**Decision**: Capture the three new per-stage timings as columns on `routing_log` — `standby_eval_ms`, `pivot_inject_ms`, `standby_transition_ms`. The existing `routing_log` per-stage timing path (spec 003 §FR-030, instrumentation per PR #163) is the canonical surface.

Adding columns to `routing_log` is a forward-only schema change (per spec 001 §FR-017). Pre-existing rows get NULL on the new columns (which is fine — the rows pre-date the standby feature).

The migration `021_participant_standby_modes.py` adds these three columns alongside the participant columns. They're all nullable `INTEGER` (milliseconds, no float precision needed for the < 100ms budgets).

## §9 — Env-var naming + validator naming

**Decision**: `SACP_STANDBY_*` prefix matching the spec name; validator functions are `validate_standby_*` matching the env-var names. This mirrors the spec-013/014/021/022/023/025/029 convention.

The four vars + ranges:

- `SACP_STANDBY_DEFAULT_WAIT_MODE` — enum `wait_for_human` / `always`, default `wait_for_human`.
- `SACP_STANDBY_FILLER_DETECTION_TURNS` — int in `[2, 100]`, default `5`.
- `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS` — int in `[60, 86400]`, default `600`.
- `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION` — int in `[0, 100]`, default `1`.

All four register in the `VALIDATORS` tuple before the spec 029 viewer validators (the existing tuple-order convention is "by spec number ascending").

## §10 — Test harness reuse

**Decision**: Reuse the existing fixtures + helpers:

- `tests/conftest.py:_participants_ddl` — gains three new columns mirroring the alembic migration (per the `feedback_test_schema_mirror` rule).
- The existing `test_022_*` / `test_025_*` test patterns (validator → architectural → endpoint → ws-event → integration) is the template for the `test_027_*` suite.
- No new test framework or fixture machinery needed.

E2E suite is skip-gated by `SACP_RUN_E2E=1` per the existing pattern. The non-E2E suite runs deterministically against the test database; no LLM provider call is required (the dispatch path is mocked via the existing `mock_litellm` fixture from spec 020's harness).

## §11 — Frontend module placement

**Decision**: Pure-logic helpers in `frontend/standby_ui.js` (UMD + Node test pattern per `frontend_polish_module_pattern` memory); render integration in `frontend/app.jsx`.

The standalone module exports:

- `formatWaitModeBadge(participant)` — returns `'wait_for_human'` / `'always'` / `null` (null when participant is a human, not an AI).
- `formatStandbyPill(participant, lastStandbyEvent)` — returns the standby-pill copy from a `participant` row + the most recent `participant_standby` WS event payload, or `null` when not in standby.
- `isLongTermObserver(participant)` — returns true when `wait_mode_metadata.long_term_observer === true`.
- `formatLongTermObserverBadge(participant)` — returns "Long-term observer — human absent" when `isLongTermObserver(participant)`, else null.

These are pure functions over participant + event data; the React rendering path in `frontend/app.jsx` calls them.

## §12 — Audit-label parity gate coordination

**Decision**: The five new audit actions register in `src/orchestrator/audit_labels.py` `LABELS` dict + `frontend/audit_labels.js` mirror in the same PR. Order in both files matches the existing convention (functional-grouping by spec number).

The five entries:

```python
"standby_entered": {"label": "Participant entered standby"},
"standby_exited": {"label": "Participant exited standby"},
"pivot_injected": {"label": "Orchestrator injected pivot message"},
"standby_observer_marked": {"label": "Participant marked long-term observer"},
"wait_mode_changed": {"label": "Participant wait_mode changed"},
```

Mirror exactly in `frontend/audit_labels.js`. The CI parity gate (`scripts/check_audit_label_parity.py` per spec 029) enforces equality.
