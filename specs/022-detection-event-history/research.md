# Research: Detection Event History Surface

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 (initial); **Amended 2026-05-11** (post §1 reversal — dedicated `detection_events` table replaces read-side join) | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Phase 0 research for spec 022. The load-bearing decision is §1 (cross-instance WS broadcast mechanism, per Clarifications §6); §§2-16 settle the remaining design choices ahead of `/speckit.tasks`. **Amendment 2026-05-11**: §§2-4 are rewritten in place to reflect the dedicated-table architecture. §§5-17 are unchanged in substance.

## §1 — Cross-instance WS broadcast mechanism (load-bearing)

**Context**: Per Clarifications §6, both `detection_event_appended` (live-update) and `detection_event_resurfaced` (operator re-surface) MUST reach the facilitator's WS regardless of which orchestrator process holds the WS connection. Spec 011's existing in-process per-session broadcast does NOT cross instances. v1 needs a routing layer.

**Options surveyed**:

- **(a) PostgreSQL LISTEN/NOTIFY**. Each orchestrator process opens a long-lived asyncpg LISTEN connection on per-session channels for facilitator subscribers it currently holds. POST emits `NOTIFY <session_channel>, '<json_payload>'`. All listeners on that channel receive the payload; only the instance holding the facilitator's WS rebroadcasts.
- **(b) Redis pub/sub**. Each instance subscribes via `redis-py` v5.x to per-session channels for facilitator subscribers it holds. POST publishes the payload to the channel. Same fan-out semantics as (a) but on Redis.
- **(c) DB-backed session→instance binding table**. New `session_instance_bindings(session_id, facilitator_id, instance_id, last_heartbeat)` table. Each instance heartbeats its bindings (default every 5s). POST resolves binding, forwards via HTTP to the bound instance's internal endpoint, which then broadcasts in-process.
- **(d) Same-process fast path only**. Reject re-surface POST if the WS is on a different instance with HTTP 503 + retry hint. Violates Clarifications §6 — rejected.

**Comparison** (load tested at the Phase 3 ceiling of 5 facilitators × 10 sessions × 2 orchestrator instances):

| Mechanism | New dependency | Cross-instance latency P95 | Operational complexity | Failure mode |
|---|---|---|---|---|
| (a) LISTEN/NOTIFY | None (asyncpg already in stack) | ~50ms (postgres roundtrip + JSON parse) | Low — one long-lived LISTEN connection per instance per session-holding-window | NOTIFY payload >8000B truncates; postgres connection pool exhaustion under high listener count |
| (b) Redis pub/sub | `redis-py` v5.x + Redis service in compose | ~10ms (memory roundtrip) | Medium — Redis service must be added to docker-compose; auth + persistence config | Redis down = re-surface fails; less battle-tested in this stack than Postgres |
| (c) DB-backed binding + HTTP forward | None | ~150ms (DB lookup + HTTP forward + DB-side audit append) | High — heartbeat protocol; cleanup-on-disconnect; HTTP internal-mesh auth | Stale binding rows on crash require TTL sweep; internal HTTP adds auth surface |

**Decision**: **Option (a) PostgreSQL LISTEN/NOTIFY** as v1 primary.

**Rationale**:
- Zero new dependencies — Postgres + asyncpg are already in the stack at the version we run (Constitution §6.3 supply-chain stance favors minimizing surface).
- The 8000-byte NOTIFY payload limit comfortably fits the broadcast envelope (event id + 5-class type + participant id + truncated 200-char snippet + score + timestamp + disposition ≈ 500B; re-surface envelope similar).
- One LISTEN connection per active session per instance is bounded by the per-instance facilitator-bind count, well under typical connection-pool ceilings at the Phase 3 ceiling.
- Cross-instance latency budget (P95 ≤ 500ms per spec §V14) absorbs the ~50ms LISTEN/NOTIFY hop with significant headroom; same-instance latency (P95 ≤ 200ms) takes the in-process fast path with no LISTEN involvement.
- Failure modes are observable in existing Postgres operator dashboards (connection pool stats, NOTIFY traffic).

**Fallback path**: If load testing reveals connection-pool pressure at deployment scale, swap to Redis pub/sub (option b). The `src/web_ui/cross_instance_broadcast.py` module abstracts the mechanism behind a `broadcast_session_event(session_id, event_payload)` interface so the swap is a single-file change. Redis becomes the v2 mechanism if NOTIFY hits a wall; the contract surface (FR-006, FR-009, SC-010) is mechanism-agnostic.

**Failure mode and recovery** (per Session 2026-05-11 Pass 1 closeout clarification): Postgres LISTEN/NOTIFY is fire-and-forget. If the receiving instance's LISTEN connection drops (asyncpg pool churn, transient network blip) at the moment a NOTIFY fires, the message is silently lost. The v1 contract is **best-effort cross-instance delivery** — FR-009 softens the live-update guarantee from "MUST deliver" to "best-effort with eventual consistency via REST refetch." Spec 011 FR-041 pins the SPA's reconciliation triggers (refetch on WS reconnect + window-focus return after inactivity threshold) so missed pushes become next-interaction-visible. SC-010 stands as a happy-path verifier (both LISTEN connections healthy); the LISTEN-dropped scenario is recovered via FR-041, not asserted as a hard MUST. Rationale: a polling subsystem or persistent broker is disproportionate to the narrow "user inactive + LISTEN dropped + new event fires" window; the refetch path already exists in the SPA for page-open and survives the cost-benefit test.

**Rejected**: Option (c) introduces a stateful heartbeat protocol with cleanup edge cases that aren't worth the latency penalty; option (d) violates Clarifications §6.

## §2 — `detection_events` page query (single-table SELECT, amended 2026-05-11)

**Context**: FR-001 requires a unified event stream. Per the Session 2026-05-11 amendment, all five event classes are persisted to a single dedicated table; the query collapses to one indexed SELECT.

**Query shape**:

```sql
SELECT
    id, session_id, event_class, participant_id, trigger_snippet,
    detector_score, turn_number, timestamp, disposition,
    last_disposition_change_at
FROM detection_events
WHERE session_id = $1
  AND ($2::timestamptz IS NULL OR timestamp >= $2)   -- since param (retention bound)
ORDER BY timestamp DESC
LIMIT $3;                                            -- max_events cap
```

**Index strategy**: Primary index on `(session_id, timestamp DESC)` covers the page query. Secondary indexes on `(session_id, event_class)` and `(session_id, participant_id)` support server-side pushdown if filter-by-type or filter-by-participant ever move server-side (v1 keeps them client-side per FR-011).

**Event id**: The `detection_events.id` (bigint primary key) is the event id. `admin_audit_log.target_id` carries the stringified id for re-surface tracking. The Session 2026-05-10 plan's synthesized `<source_table>:<source_row_id>` identifier is obsolete after the amendment.

**Disposition resolution**: The table denormalizes the latest disposition into the `disposition` column. UPDATEs on this column are the only write side-effect of disposition transition handling (the transition rows themselves still append to `admin_audit_log` per FR-010 for full audit trail). The page query never re-derives the latest disposition; it just reads the column.

## §3 — `detection_events` table schema (amended 2026-05-11)

**Context**: The dedicated table replaces the read-side join. One alembic migration adds the table + three indexes; `tests/conftest.py` raw DDL mirrors the migration per `feedback_test_schema_mirror`.

**Migration shape** (`alembic/versions/017_detection_events.py`):

```sql
CREATE TABLE detection_events (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,                          -- no FK per spec 007 pattern (survives session deletion)
    event_class TEXT NOT NULL,                         -- one of: ai_question_opened, ai_exit_requested,
                                                       --        density_anomaly, mode_recommendation, mode_change
    participant_id TEXT NOT NULL,                      -- AI id for question/exit/density; facilitator id for mode events
    trigger_snippet TEXT,                              -- nullable for mode events
    detector_score REAL,                               -- nullable for binary detectors and mode events
    turn_number INTEGER,                               -- nullable for mode events not tied to a turn
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disposition TEXT NOT NULL DEFAULT 'pending',       -- one of: pending, banner_acknowledged, banner_dismissed, auto_resolved
    last_disposition_change_at TIMESTAMPTZ,            -- NULL until first transition
    CONSTRAINT detection_events_class_check CHECK (event_class IN
        ('ai_question_opened', 'ai_exit_requested', 'density_anomaly',
         'mode_recommendation', 'mode_change')),
    CONSTRAINT detection_events_disposition_check CHECK (disposition IN
        ('pending', 'banner_acknowledged', 'banner_dismissed', 'auto_resolved'))
);

CREATE INDEX detection_events_session_timestamp_idx
    ON detection_events (session_id, timestamp DESC);
CREATE INDEX detection_events_session_class_idx
    ON detection_events (session_id, event_class);
CREATE INDEX detection_events_session_participant_idx
    ON detection_events (session_id, participant_id);
```

**No FK to sessions or participants** mirrors the spec 007 pattern for `admin_audit_log` — detection events outlive their referenced session for audit purposes.

**Existing source-table schema audit** (informational, since the migration's call-site sweep dual-writes from the existing emit sites; the existing tables remain unchanged):

- **`routing_log`** (per alembic 001): `id`, `session_id`, `turn_number`, `intended_participant`, `actual_participant`, `routing_action`, `complexity_score`, `domain_match`, `reason`, `timestamp`. Used by the question/exit emit-site call sweep ONLY to derive turn_number + participant_id for the `detection_events` row INSERT — the routing_log row itself stays unchanged.
- **`convergence_log`** (per alembic 010): `(turn_number, session_id, tier, density_value, baseline_value, embedding, similarity_score, divergence_prompted)`. Used by the density-anomaly emit-site call sweep ONLY to derive turn_number + density_value (becomes detection_score in detection_events) — the convergence_log row stays unchanged.
- **`admin_audit_log`** (per alembic 001 + 014): `id`, `session_id`, `facilitator_id`, `action`, `target_id`, `previous_value`, `new_value`, `timestamp`. Used by the mode-event emit-site call sweep ONLY to derive facilitator_id + timestamp — the admin_audit_log row stays unchanged. Re-surface POST writes a NEW admin_audit_log row with `action='detection_event_resurface'` and `target_id=<detection_events.id>::text` per FR-006.

## §4 — Disposition resolution logic (amended 2026-05-11)

**Context**: FR-010 requires the panel to surface the latest disposition for each event from the four-value enum. With the dedicated table, the latest disposition is denormalized into `detection_events.disposition` (default `'pending'`). Disposition transitions update that column AND append a transition row to `admin_audit_log`.

**Mapping** (`admin_audit_log.action` → effect on `detection_events.disposition`):

| `admin_audit_log.action` | Effect | Notes |
|---|---|---|
| `detection_event_acknowledged` | UPDATE `disposition='banner_acknowledged'`, set `last_disposition_change_at=NOW()` | |
| `detection_event_dismissed` | UPDATE `disposition='banner_dismissed'`, set `last_disposition_change_at=NOW()` | |
| `detection_event_auto_resolved` | UPDATE `disposition='auto_resolved'`, set `last_disposition_change_at=NOW()` | written by auto-resolution sweep (spec 004 for density-anomaly threshold drop) |
| `detection_event_resurface` | No UPDATE to `disposition` | preserved alongside the existing disposition; broadcast triggers banner reappearance |

The dual-write is wrapped in a single transaction (UPDATE detection_events + INSERT admin_audit_log row); a failure rolls back both halves.

**Disposition timeline** (FR-010): A click-to-expand view of an event's row queries `admin_audit_log` for ALL rows with `target_id=<detection_events.id>::text` AND `action LIKE 'detection_event_%'` ordered ascending, showing the operator the full transition history (including re-surface entries). This is a second endpoint call, NOT a join in the page query — only fetched on click-expand to keep the page query bounded.

## §5 — Five-class event-class registry

**Context**: Per Clarifications §3, the v1 taxonomy is fixed. The registry maps source-table + source-row attributes → one of five panel classes.

**Backend registry** (`src/web_ui/detection_events.py`):

```python
EVENT_CLASSES: dict[str, dict[str, str]] = {
    "ai_question_opened": {"label": "AI question opened",   "source": "routing_log",      "predicate": "detector_kind = 'question'"},
    "ai_exit_requested":  {"label": "AI exit requested",    "source": "routing_log",      "predicate": "detector_kind = 'exit'"},
    "density_anomaly":    {"label": "Density anomaly",      "source": "convergence_log",  "predicate": "tier = 'density_anomaly'"},
    "mode_recommendation":{"label": "Mode recommendation",  "source": "admin_audit_log",  "predicate": "action = 'mode_recommendation'"},
    "mode_change":        {"label": "Mode change",          "source": "admin_audit_log",  "predicate": "action = 'mode_change'"},
}
```

**Frontend mirror** (`frontend/detection_event_taxonomy.js`): UMD module exporting `EVENT_CLASSES` with `key + label` only (predicate and source columns are server-side concerns). Parity gate (§16) enforces key-set + label-string equality.

**Future additions** require both a spec amendment AND a coordinated backend+frontend module update; the parity gate fails if drift occurs.

## §6 — Spec 014 action-string → panel-class mapping

**Context**: Spec 014 (Implemented 2026-05-08) writes `action='mode_recommendation'` and `action='mode_change'` rows to `admin_audit_log`. Per Clarifications §8, these surface as two DISTINCT panel classes (not merged under one).

**Mapping**: Direct passthrough — `admin_audit_log.action` value IS the panel-class key for these two rows. The class-mapping registry §5 documents the identity mapping. No translation table needed; if spec 014 ever adds a third mode-event action string (e.g., `mode_change_reverted`), it requires a spec 022 amendment to add the new class to the registry (taxonomy is fixed per Clarifications §3).

## §7 — Re-surface admin_audit_log row shape (amended 2026-05-11)

**Context**: FR-006 requires the re-surface action to emit one `admin_audit_log` row. The amendment aligns the column names with the existing `admin_audit_log` schema.

**Row shape**:

```
action         = 'detection_event_resurface'
session_id     = <session>
facilitator_id = <facilitator who clicked re-surface>
target_id      = <detection_events.id>::text   (stringified bigint per the column's TEXT type)
previous_value = NULL
new_value      = NULL
timestamp      = NOW()
```

Per §4 amendment, `detection_event_resurface` does NOT update `detection_events.disposition` — the row stays at its existing disposition. The re-surface is a forensic-trail event AND a WS broadcast trigger only.

**Disposition timeline lookup**:

```sql
SELECT action, facilitator_id, timestamp
FROM admin_audit_log
WHERE session_id = $1
  AND target_id = $2::text
  AND action IN ('detection_event_acknowledged',
                 'detection_event_dismissed',
                 'detection_event_auto_resolved',
                 'detection_event_resurface')
ORDER BY timestamp ASC;
```

This is the click-expand fetch; not joined into the page query.

## §8 — Filter implementation (client-side AND-compose)

**Context**: FR-011 ships four client-side filter axes composing with AND semantics. Spec 029 established the client-side filter pattern for the audit-log viewer; spec 022 follows it.

**Axes**:

- **Type filter**: dropdown of 5 class keys + `all`. Selecting a class hides all other classes.
- **Participant filter**: dropdown of session participants + `all`. Selecting a participant hides events for other participants. Participant list is derived from the loaded event set's `participant_id` column (NOT a separate fetch — keeps it bounded).
- **Time-range filter**: two date-time inputs (from + to); either may be open. Default both open (no range). Filter compares against the event's `timestamp`.
- **Disposition filter**: dropdown of 4 values + `all`. Selecting a value hides events with other dispositions.

**Composition**: an event displays iff `type_match AND participant_match AND timerange_match AND disposition_match`. All four axes evaluate independently; the implementation is a single `Array.prototype.filter()` call with a four-predicate body. Performance is O(N) over loaded events where N ≤ `SACP_DETECTION_HISTORY_MAX_EVENTS` (default unbounded for active session, expected ≤ 100s).

**Hidden-event badge** (FR-011-related): per scenario 3 of US3, a small badge on each filter control increments with the count of events outside the active filter. The badge is also O(N) over the loaded set.

## §9 — Time-range filter UX

**Context**: Time-range is a new filter axis introduced at Clarifications §4. UX patterns considered:

- **(a) Absolute date-time inputs (from + to)**. Native `<input type="datetime-local">` for both bounds. Pros: precise; familiar. Cons: clunky for "last 5 minutes" use case.
- **(b) Relative offset chips (last 5m / 15m / 1h / all)**. One-click presets. Pros: matches the diagnostic "what happened around turn N" workflow. Cons: doesn't support arbitrary ranges.
- **(c) Both — preset chips + collapsible absolute inputs**. Pros: covers both use cases. Cons: more UI surface.

**Decision**: **(c) Both**. v1 ships four preset chips (`5m`, `15m`, `1h`, `all`) plus a collapsible "custom range" panel with two date-time inputs. The chips default to `all`; selecting a chip updates the bounds inline. Custom-range panel toggles bounded by a "Custom" link. Rationale: the diagnostic workflow is the primary use case (presets win) but the "session debrief 2 hours later" workflow needs arbitrary ranges. Total UI surface ≈ one row of controls in the filter bar.

## §10 — WS event shape (consistency with spec 029)

**Context**: Spec 029 ships the `audit_log_appended` WS event pattern with role-filtered broadcast. Spec 022 introduces two new WS events: `detection_event_appended` (live-update) and `detection_event_resurfaced` (re-surface broadcast). Both follow the same pattern.

**Event shape** (`detection_event_appended`):

```json
{
  "type": "detection_event_appended",
  "session_id": "<session>",
  "event": {
    "event_id": "<source_table>:<source_row_id>",
    "event_class": "ai_question_opened",
    "event_class_label": "AI question opened",
    "participant_id": "<participant>",
    "trigger_snippet": "...",
    "detector_score": 0.87,
    "timestamp": "2026-05-10T14:32:01.234Z",
    "disposition": "pending"
  }
}
```

**Re-surface event shape** (`detection_event_resurfaced`): same envelope but `type='detection_event_resurfaced'` and the `event` payload includes the original banner content (re-broadcast verbatim). Recipient: facilitator only — role-filtered via `broadcast_to_session_roles(session_id, ['facilitator'], payload)`.

## §11 — Re-surface broadcast: target audience (facilitator-only)

**Context**: Per Clarifications §2, re-surface re-broadcasts to the facilitator's WS, NOT the participant's WS. The drafted FR-006 wording said "over the participant's WS channel" — this is incorrect and is corrected in the updated FR-006 text (and re-confirmed here for the contracts doc).

The role-filtered broadcast call site is `broadcast_to_session_roles(session_id, ['facilitator'], payload)`, identical to spec 029's `audit_log_appended` call. Cross-instance routing (§1) honors the role filter on both ends — the receiving instance only delivers to facilitator WS subscribers it holds.

## §12 — Sort order decision (newest-first vs. oldest-first)

**Context**: The spec's US1 acceptance scenario 2 says "oldest first OR newest first per `/speckit.plan` decision; one ordering, not a mix." Pre-clarify left this open.

**Decision**: **Newest first by default**. Rationale: the primary use case is "what just happened?" — a facilitator opens the panel after noticing a downstream effect and wants to see the most recent events first. The "what happened around turn N" reconstruction use case is served equally well by either order plus the time-range filter (§9). Newest-first matches spec 029's audit-log viewer default, keeping the panel families consistent.

**Configurable**: a single sort-toggle button in the filter bar allows the operator to flip to oldest-first for the timeline-replay use case. Sort is client-side over the loaded set (no server round-trip).

## §13 — Empty-state and unregistered-class handling

**Context**: Two failure modes need explicit UI:

- **No events**: session has zero detection events. Per spec acceptance scenario US1.3, render an empty-state message ("No detection events for this session yet") rather than a blank panel.
- **Filter excludes all**: session has events but the active filter set hides them all. Render "No events match the active filters" with a "Clear filters" affordance.
- **Unregistered event class**: a future source-table addition (e.g., a new spec adds rows to `routing_log` with `detector_kind='something_new'` before the 022 registry is amended). The UNION-ALL would surface the row but the class-mapping would return `[unregistered: <raw>]`. Spec 029's pattern is used: render the row with the `[unregistered: ...]` label and emit a WARN-level orchestrator log entry so registry drift is observable.

## §14 — Trigger snippet truncation and expand

**Context**: FR-012 requires a display length cap (target 200 chars) with click-to-expand. Server returns the full snippet; truncation is client-side so expand is local.

**Implementation**: each event row renders a `TruncatedSnippet` component (inline in `frontend/app.jsx`) showing the first 200 chars + `...` if longer, with a `[expand]` link toggling the full snippet inline. The full snippet is preserved on the event row's JS state — no fetch on expand.

**Privacy/security note**: the snippet is already in the source table's row and is exposed via spec 010 debug-export under the same facilitator authorization. The panel adds no new content exposure; it adds a navigable surface for the same content.

## §15 — V14 performance budget instrumentation

**Context**: Spec §V14 declares five budgets. Each MUST be observable in structured logs.

**Hooks**:

- **Panel load**: `log_repo.get_detection_events_page` wraps the query in `time.perf_counter()`; emits `detection_events.page_load_ms` to the access log alongside the existing per-tool latency log (spec 006 §FR-018).
- **WS push**: the `events.py` emitter records timestamp at source-row INSERT and at WS payload send; the receiving client records timestamp at rendered. The 100ms server-side budget is enforced; client-side render-time is informational.
- **Re-surface same-instance**: `detection_events.py` endpoint records start → broadcast-send timestamp; emits `detection_events.resurface_same_instance_ms`.
- **Re-surface cross-instance**: `cross_instance_broadcast.py` records start → NOTIFY-sent timestamp on the POST side AND records NOTIFY-received → broadcast-send timestamp on the receiving side. Both emit to structured logs; budget enforcement is the sum.
- **Filter application**: client-side `Date.now()` deltas around the `Array.prototype.filter()` call; logged to browser console at DEBUG verbosity only (not server-side).

## §16 — Parity gate for detection_event_taxonomy

**Context**: Following spec 029's audit-label parity gate pattern. Backend `EVENT_CLASSES: dict[str, dict[str, str]]` in `src/web_ui/detection_events.py` is the source of truth; frontend `EVENT_CLASSES` in `frontend/detection_event_taxonomy.js` mirrors keys + labels.

**Gate**: `scripts/check_detection_taxonomy_parity.py` (new) parses the JS module's `EVENT_CLASSES = {...}` literal with a small state-machine parser (reuse the pattern from spec 029's `check_audit_label_parity.py`), compares key-set + label-string parity, exits 1 with a structured error on drift. Wired into the CI workflow as a required-passing check at T011-equivalent.

**Drift failure mode**: backend adds a 6th class (e.g., for spec 021 filler-retry events) but the frontend mirror isn't updated. Gate fails; PR is blocked until the frontend module is updated.

## §17 — Test fixture strategy

**Context**: Tests need events of all 5 classes in a known session.

**Fixture pattern** (in `tests/conftest.py` or per-test fixtures):

- `routing_log_question_event(session_id, participant_id)` — INSERT one row with `detector_kind='question'`.
- `routing_log_exit_event(session_id, participant_id)` — INSERT one row with `detector_kind='exit'`.
- `convergence_log_density_anomaly_event(session_id, participant_id)` — INSERT one row with `tier='density_anomaly'`.
- `admin_audit_log_mode_recommendation_event(session_id, actor_id)` — INSERT one row with `action='mode_recommendation'`.
- `admin_audit_log_mode_change_event(session_id, actor_id)` — INSERT one row with `action='mode_change'`.

The five fixtures compose into a "full-taxonomy session" fixture used by SC-001 e2e and the filter-composition tests.

**Cross-instance test fixture**: a two-process pytest fixture that:
1. Starts orchestrator process A on port X
2. Starts orchestrator process B on port Y, sharing the same Postgres DB
3. Opens a facilitator WS on process B
4. Issues a re-surface POST against process A
5. Asserts the WS on process B receives the `detection_event_resurfaced` payload within the cross-instance budget

This fixture runs only when both ports are reservable and Postgres is available; skipped in CI environments without Docker (Windows local dev) via the existing `@pytest.mark.requires_postgres` marker.

## Outstanding from clarify (none)

All eight initial-draft markers resolved in Session 2026-05-10. No deferred items.

## Summary

Sixteen Phase 0 research items resolved. The load-bearing decision (§1 cross-instance broadcast mechanism = Postgres LISTEN/NOTIFY with Redis pub/sub as documented v2 fallback) is settled. The query shape (§2), schema audit (§3), disposition resolution (§4), and five-class registry (§5) define the data surface. The filter implementation (§8), time-range UX (§9), and WS event shapes (§10-11) define the client surface. Sort order (§12), empty-state handling (§13), snippet truncation (§14), perf instrumentation (§15), parity gate (§16), and test fixtures (§17) round out the implementation contract. Ready for `/speckit.tasks` once data-model.md and contracts/ land.
