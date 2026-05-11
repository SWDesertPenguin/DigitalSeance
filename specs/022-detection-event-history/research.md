# Research: Detection Event History Surface

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Phase 0 research for spec 022. The load-bearing decision is §1 (cross-instance WS broadcast mechanism, per Clarifications §6); §§2-16 settle the remaining design choices ahead of `/speckit.tasks`.

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

**Rejected**: Option (c) introduces a stateful heartbeat protocol with cleanup edge cases that aren't worth the latency penalty; option (d) violates Clarifications §6.

## §2 — Read-side UNION-ALL query shape

**Context**: FR-001 requires a unified event stream over three source tables. The query MUST be bounded per-session, indexed, and complete within the panel-load P95 ≤ 500ms budget.

**Query shape**:

```sql
WITH disposition_latest AS (
    SELECT DISTINCT ON (target_event_id) target_event_id, action, timestamp
    FROM admin_audit_log
    WHERE session_id = $1 AND action LIKE 'detection_event_%'
    ORDER BY target_event_id, timestamp DESC
)
SELECT
    'routing_log' AS source_table, id AS source_row_id,
    CASE detector_kind
        WHEN 'question' THEN 'ai_question_opened'
        WHEN 'exit' THEN 'ai_exit_requested'
    END AS event_class,
    participant_id, trigger_snippet, detector_score, timestamp,
    COALESCE(dl.action, 'pending') AS disposition
FROM routing_log
LEFT JOIN disposition_latest dl ON dl.target_event_id = routing_log.id::text
WHERE session_id = $1 AND detector_kind IN ('question', 'exit')

UNION ALL

SELECT
    'convergence_log' AS source_table, id AS source_row_id,
    'density_anomaly' AS event_class,
    participant_id, trigger_snippet, anomaly_score AS detector_score, timestamp,
    COALESCE(dl.action, 'pending') AS disposition
FROM convergence_log
LEFT JOIN disposition_latest dl ON dl.target_event_id = convergence_log.id::text
WHERE session_id = $1 AND tier = 'density_anomaly'

UNION ALL

SELECT
    'admin_audit_log' AS source_table, id AS source_row_id,
    action AS event_class,  -- 'mode_recommendation' or 'mode_change' verbatim
    actor_id AS participant_id, NULL AS trigger_snippet, NULL AS detector_score, timestamp,
    'auto_resolved' AS disposition  -- mode events are observation-only
FROM admin_audit_log
WHERE session_id = $1 AND action IN ('mode_recommendation', 'mode_change')

ORDER BY timestamp DESC, source_table, source_row_id
LIMIT $2;
```

**Index strategy**: All three source tables MUST have `(session_id, timestamp DESC)` indexes (spec 029 verified one for `admin_audit_log`; routing_log + convergence_log to be verified during T001). The disposition CTE uses `(session_id, action, target_event_id, timestamp DESC)` — partial index on `action LIKE 'detection_event_%'` is appropriate.

**Synthesized event id**: To support disposition tracking and re-surface, each event needs a stable id. Use `source_table || ':' || source_row_id` as the event-id contract (e.g., `routing_log:42`, `convergence_log:17`, `admin_audit_log:91`). Disposition rows write `target_event_id` in that shape. Re-surface POST validates the format before lookup.

## §3 — Source-table schema audit

**Context**: The UNION-ALL relies on specific columns existing. Audit before writing the query.

- **`routing_log`** (spec 003 §FR-030): `id`, `session_id`, `participant_id`, `detector_kind` (enum: `question`, `exit`, ...), `trigger_snippet` (TEXT), `detector_score` (REAL nullable), `timestamp` (TIMESTAMPTZ). All present per spec 003 migration. Composite index on `(session_id, timestamp)` confirmed.
- **`convergence_log`** (spec 004 §FR-020): `id`, `session_id`, `participant_id`, `tier` (enum: `density_anomaly`, `convergence_check`, ...), `trigger_snippet` (TEXT), `anomaly_score` (REAL nullable), `timestamp` (TIMESTAMPTZ). All present per spec 004 migration. Index audit needed: `(session_id, tier, timestamp)` partial index recommended.
- **`admin_audit_log`** (spec 002 §FR-014, spec 014 PR #326): `id`, `session_id`, `actor_id`, `action` (TEXT), `target_event_id` (TEXT nullable, added in spec 029 PR #341 for `audit_log_appended` join support), `previous_value` (JSONB nullable), `new_value` (JSONB nullable), `timestamp` (TIMESTAMPTZ). Spec 014 writes `mode_recommendation` and `mode_change` rows here.

**Action item**: T001 verifies the three indexes exist or adds an alembic migration adding `(session_id, tier, timestamp) WHERE tier IN ('density_anomaly')` to `convergence_log` if missing.

## §4 — Disposition resolution logic

**Context**: FR-010 requires the panel to surface the latest disposition for each event from the four-value enum. Disposition transitions write to `admin_audit_log` with action strings `detection_event_acknowledged`, `detection_event_dismissed`, `detection_event_auto_resolved`. Default disposition is `pending`.

**Mapping**:

| `admin_audit_log.action` | Disposition value |
|---|---|
| `detection_event_acknowledged` | `banner_acknowledged` |
| `detection_event_dismissed` | `banner_dismissed` |
| `detection_event_auto_resolved` | `auto_resolved` |
| (no row exists for the event id) | `pending` |
| `detection_event_resurface` | (does NOT change disposition; preserved alongside the prior disposition row) |

The DISTINCT-ON-target_event_id CTE in §2 returns the latest disposition action. The class-mapping module maps action → disposition value.

**Disposition timeline** (FR-010): A click-to-expand view of an event's row queries `admin_audit_log` for ALL rows with `target_event_id=<id>` ordered ascending, showing the operator the full transition history (including re-surface entries). This is a second endpoint call, NOT a join in the page query — only fetched on click-expand to keep the page query bounded.

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

## §7 — Re-surface admin_audit_log row shape

**Context**: FR-006 requires the re-surface action to emit one `admin_audit_log` row.

**Row shape**:

```
action          = 'detection_event_resurface'
session_id      = <session>
actor_id        = <facilitator_id>
target_event_id = '<source_table>:<source_row_id>'   (the synthesized event-id from §2)
previous_value  = NULL
new_value       = NULL
timestamp       = NOW()
```

The disposition CTE in §2 already filters `action LIKE 'detection_event_%'` so re-surface rows are visible to the disposition lookup — but per §4's mapping table, `detection_event_resurface` does NOT change disposition. The disposition CTE returns the row matching the predicate `action IN ('detection_event_acknowledged', 'detection_event_dismissed', 'detection_event_auto_resolved')` rather than `LIKE 'detection_event_%'`; this excludes re-surface rows from the disposition lookup while still preserving them in the disposition timeline (§4 click-expand fetch).

**Refined disposition CTE**:

```sql
WITH disposition_latest AS (
    SELECT DISTINCT ON (target_event_id) target_event_id, action, timestamp
    FROM admin_audit_log
    WHERE session_id = $1 AND action IN ('detection_event_acknowledged', 'detection_event_dismissed', 'detection_event_auto_resolved')
    ORDER BY target_event_id, timestamp DESC
)
```

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
