# Data Model: Detection Event History Surface

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

Spec 022's data surface is a **read-side projection** over three existing append-only log tables. No new persisted entities. No schema changes to existing tables for the panel surface itself. The cross-instance broadcast mechanism (`research.md §1`) uses Postgres LISTEN/NOTIFY which adds no persisted state.

## Read-side projection: `DetectionEvent`

`DetectionEvent` is a virtual entity assembled at query time by `src/repositories/log_repo.py::get_detection_events_page`. It does NOT exist as a persisted row. The columns of the projection:

| Field | Type | Source | Notes |
|---|---|---|---|
| `event_id` | TEXT | Synthesized | `<source_table>:<source_row_id>` (e.g., `routing_log:42`). Stable across re-fetches; used as the `target_event_id` for disposition and re-surface rows. |
| `event_class` | TEXT (enum) | Derived | One of five fixed values: `ai_question_opened`, `ai_exit_requested`, `density_anomaly`, `mode_recommendation`, `mode_change`. Per the §5 class-mapping registry in `src/web_ui/detection_events.py`. |
| `event_class_label` | TEXT | Derived | Human-readable label from the class registry. Mirrored on the frontend (`frontend/detection_event_taxonomy.js`) with the parity gate. |
| `participant_id` | TEXT | `routing_log.participant_id` OR `convergence_log.participant_id` OR `admin_audit_log.actor_id` | For mode events the actor_id is the facilitator who triggered the recommendation/change. |
| `trigger_snippet` | TEXT (nullable) | `routing_log.trigger_snippet` OR `convergence_log.trigger_snippet` OR NULL | NULL for mode events (no snippet content). Display-truncated client-side to 200 chars per FR-012. |
| `detector_score` | REAL (nullable) | `routing_log.detector_score` OR `convergence_log.anomaly_score` OR NULL | NULL for mode events and for binary detectors that fire without a score. |
| `timestamp` | TIMESTAMPTZ | Source row | UTC; formatted via spec 029's `src/orchestrator/time_format.py::format_iso` for output. |
| `disposition` | TEXT (enum) | Derived | One of four: `pending`, `banner_acknowledged`, `banner_dismissed`, `auto_resolved`. Latest disposition-transition row from `admin_audit_log` per `research.md §4`. Mode events default to `auto_resolved`. |
| `source_table` | TEXT | Synthesized | `routing_log`, `convergence_log`, or `admin_audit_log`. Surfaces in the response for V18 derived-artifact traceability — reviewers can walk from `event_class` back to the canonical source. |
| `source_row_id` | INTEGER | Source row | The raw id; combined with `source_table` to form `event_id`. |

**Sort order**: `(timestamp DESC, source_table, source_row_id)` by default per `research.md §12`. Client toggle flips to ASC; sort is client-side after page load.

## Disposition transition rows (existing)

Disposition transitions are written to `admin_audit_log` by the existing US1/banner-handling code paths (these rows already exist for events that have been acknowledged or dismissed; spec 022 only READS them). Spec 022 adds a new disposition transition for the re-surface action (see "Re-surface action row" below).

| `admin_audit_log.action` | Maps to disposition | Written by |
|---|---|---|
| `detection_event_acknowledged` | `banner_acknowledged` | Existing US1/banner-acknowledge handler (spec 011) |
| `detection_event_dismissed` | `banner_dismissed` | Existing US1/banner-dismiss handler (spec 011) |
| `detection_event_auto_resolved` | `auto_resolved` | Auto-resolution sweep (spec 004 for density-anomaly threshold-drop; future detectors for theirs) |
| `detection_event_resurface` | (does NOT change disposition; preserved alongside) | NEW — written by FR-006 re-surface POST in spec 022 |

The disposition CTE in `research.md §2/§7` reads only the first three actions; `detection_event_resurface` is visible in the disposition timeline (click-expand fetch) but does NOT mutate the displayed disposition.

## Re-surface action row (new)

The only new write spec 022 introduces is the re-surface audit row, appended to `admin_audit_log` per FR-006.

| Column | Value |
|---|---|
| `id` | auto-generated bigint |
| `session_id` | the target event's session_id |
| `actor_id` | the facilitator who clicked re-surface (from the authenticated session) |
| `action` | `detection_event_resurface` (literal) |
| `target_event_id` | `<source_table>:<source_row_id>` of the re-surfaced event |
| `previous_value` | NULL |
| `new_value` | NULL |
| `timestamp` | NOW() at the time of the POST |

This is an APPEND, not a mutation. Spec 001 §FR-008 append-only invariant on `admin_audit_log` is preserved.

## Class-mapping registry (process-scope, hardcoded)

`src/web_ui/detection_events.py::EVENT_CLASSES` is the source-of-truth dictionary mapping panel-class keys to display labels and source-table predicates. Per `research.md §5`:

```python
EVENT_CLASSES: dict[str, dict[str, str]] = {
    "ai_question_opened":  {"label": "AI question opened",   "source": "routing_log",     "predicate": "detector_kind = 'question'"},
    "ai_exit_requested":   {"label": "AI exit requested",    "source": "routing_log",     "predicate": "detector_kind = 'exit'"},
    "density_anomaly":     {"label": "Density anomaly",      "source": "convergence_log", "predicate": "tier = 'density_anomaly'"},
    "mode_recommendation": {"label": "Mode recommendation",  "source": "admin_audit_log", "predicate": "action = 'mode_recommendation'"},
    "mode_change":         {"label": "Mode change",          "source": "admin_audit_log", "predicate": "action = 'mode_change'"},
}
```

The frontend mirror at `frontend/detection_event_taxonomy.js` exports the same keys with the `label` field only. The parity gate at `scripts/check_detection_taxonomy_parity.py` (CI required) enforces equality of key-set and label strings between the two modules.

**Mutability**: Process-scope read-only. Adding a class requires both modules to be updated coordinately AND a spec amendment (Clarifications §3 — fixed taxonomy, not extensible registry).

## Session-instance binding (Postgres LISTEN/NOTIFY — research §1)

Per `research.md §1`, cross-instance routing uses Postgres LISTEN/NOTIFY rather than a binding table. No persisted state. Each orchestrator process maintains an in-memory map of `session_id → list[facilitator_ws_connection]` (already exists per spec 011's per-session broadcast). On startup, each process opens one asyncpg `LISTEN` connection that subscribes to a single channel per active session as facilitators bind to it; on facilitator disconnect, the LISTEN is closed for that session.

**Channel naming**: `detection_events_{session_id}`. Per-session channel keeps fan-out bounded; cross-session traffic is rejected at the database level by Postgres's channel scoping.

**NOTIFY payload**: JSON envelope ≤ 7000 bytes (under the 8000-byte LISTEN limit per Postgres docs). The envelope:

```json
{
  "kind": "appended" | "resurfaced",
  "event_id": "<source_table>:<source_row_id>",
  "event_class": "ai_question_opened",
  "event_class_label": "AI question opened",
  "participant_id": "<participant>",
  "trigger_snippet": "...",                  // truncated server-side to 1000 chars before NOTIFY; client refetches full snippet via REST if longer
  "trigger_snippet_truncated": true | false,
  "detector_score": 0.87,
  "timestamp": "2026-05-10T14:32:01.234Z",
  "disposition": "pending"
}
```

**Truncation note**: The 8000-byte NOTIFY limit constrains the snippet payload size. For snippets > 1000 chars, the NOTIFY carries a truncated version and a flag; the client refetches the full event row via a REST GET on click-expand. Most snippets are under 200 chars by detector design, so this fallback is rare.

## Index audit (action item for tasks)

Per `research.md §3`, the query relies on three indexes:

- `routing_log(session_id, timestamp DESC)` — verify exists; spec 003 migration should have created it.
- `convergence_log(session_id, tier, timestamp DESC) WHERE tier = 'density_anomaly'` — partial index recommended; verify or add.
- `admin_audit_log(session_id, timestamp DESC)` — confirmed exists per spec 029 T004.
- `admin_audit_log(target_event_id, timestamp DESC) WHERE action LIKE 'detection_event_%'` — partial index for the disposition CTE; verify or add.

If any are missing, ship a single alembic migration adding all missing indexes in this feature's task list. Mirror in `tests/conftest.py` raw DDL per `feedback_test_schema_mirror`.

## V18 derived-artifact traceability

Both `event_class` and `disposition` are display-time derivations. The API response carries both the derived field AND the canonical source attribution (`source_table`, `source_row_id`, and for disposition: the latest `admin_audit_log` row's id and action) so reviewers can walk from the displayed value back to the canonical source row verbatim. The class-mapping registry IS the derivation method; the disposition CTE IS the derivation method; both are documented in `research.md §4/§5`.
