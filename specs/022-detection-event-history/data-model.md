# Data Model: Detection Event History Surface

**Branch**: `022-detection-event-history` | **Date**: 2026-05-10 (initial); **Amended 2026-05-11** (§1 reversal — DetectionEvent becomes a persisted entity in a new `detection_events` table) | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

Spec 022's data surface (post-amendment 2026-05-11) centers on a NEW `detection_events` table that the four detector emit sites dual-write to. One alembic migration adds the table + three indexes. The cross-instance broadcast mechanism (`research.md §1`) uses Postgres LISTEN/NOTIFY which adds no persisted state.

## Persisted entity: `detection_events`

Source-of-truth table for the five-class taxonomy. Schema:

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `id` | BIGSERIAL | NOT NULL (PK) | Stable event id used by FR-006 re-surface path; carried verbatim in WS payloads. |
| `session_id` | TEXT | NOT NULL | No FK to `sessions` — survives session deletion for audit (mirrors spec 007 pattern on `admin_audit_log`). |
| `event_class` | TEXT | NOT NULL | One of five fixed values: `ai_question_opened`, `ai_exit_requested`, `density_anomaly`, `mode_recommendation`, `mode_change`. CHECK constraint enforced at the DB. |
| `participant_id` | TEXT | NOT NULL | AI participant id for question/exit/density; facilitator id for mode events. No FK (consistent with spec 007). |
| `trigger_snippet` | TEXT | NULL allowed | Up to ~10KB; truncated at WS broadcast time to 1000 chars (per `data-model.md` payload size limit). NULL for mode events. |
| `detector_score` | REAL | NULL allowed | NULL for binary detectors (question/exit) and for mode events. Density-anomaly scores carry the `density_value` from `convergence_log`. |
| `turn_number` | INTEGER | NULL allowed | NULL for mode events not tied to a turn. |
| `timestamp` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Sort key for chronological ordering; primary index. |
| `disposition` | TEXT | NOT NULL DEFAULT 'pending' | Denormalized latest disposition. CHECK constraint: `pending`, `banner_acknowledged`, `banner_dismissed`, `auto_resolved`. UPDATE-able only by the disposition-transition handler. |
| `last_disposition_change_at` | TIMESTAMPTZ | NULL allowed | NULL until the first transition. |

### Indexes

| Index | Columns | Purpose |
|---|---|---|
| Primary key | `id` | bigserial auto |
| `detection_events_session_timestamp_idx` | `(session_id, timestamp DESC)` | Page query — `WHERE session_id = $1 ORDER BY timestamp DESC LIMIT $2` |
| `detection_events_session_class_idx` | `(session_id, event_class)` | Future server-side type filter / per-class stats |
| `detection_events_session_participant_idx` | `(session_id, participant_id)` | Future server-side participant filter / per-AI stats |

### Append-only semantics

INSERTs at the four emit sites; UPDATEs ONLY on `(disposition, last_disposition_change_at)` from the disposition-transition handler. No DELETEs. The append-only invariant on event content (everything except the latest-state disposition column) is preserved. The full disposition transition history flows through `admin_audit_log` (see "Transition rows" below) so the operator can reconstruct who-changed-what-when even though the table stores only the latest state.

## Dual-write contract (FR-017)

Each of the four detector emit sites issues:

1. INSERT into `detection_events` with the per-class column values.
2. Broadcast the existing per-class WS event (`ai_question_opened` / `ai_exit_requested` / `density_anomaly` / spec 014 mode events).
3. NEW: broadcast `detection_event_appended` with the inserted row's id + class + columns (per `contracts/ws-events.md`).

If the INSERT fails (DB unavailable), the existing WS broadcast still fires (preserves the current banner UX) and the failure is logged as a security-event so the gap is observable. The history panel will be missing that event until the orchestrator restarts and a replay mechanism back-fills (deferred — Phase 4 if it becomes operationally needed).

Emit sites:

| Emit site | Detector | event_class written |
|---|---|---|
| [src/orchestrator/loop.py](../../src/orchestrator/loop.py) `_detect_signals` (question branch) | A2 question tracker | `ai_question_opened` |
| [src/orchestrator/loop.py](../../src/orchestrator/loop.py) `_detect_signals` (exit branch) | A3 exit detector | `ai_exit_requested` |
| [src/orchestrator/density.py](../../src/orchestrator/density.py) anomaly detection path | Density anomaly | `density_anomaly` |
| Spec 014 mode-event emit site (advisory) | DMA controller | `mode_recommendation` |
| Spec 014 mode-event emit site (auto-apply) | DMA controller | `mode_change` |

## Transition rows (existing `admin_audit_log`)

Disposition transitions append to `admin_audit_log` (existing append-only table; spec 022 makes no schema changes here). Spec 022 introduces the action string `detection_event_resurface`; the other three transition action strings (`detection_event_acknowledged`, `detection_event_dismissed`, `detection_event_auto_resolved`) are written by existing US1/auto-resolve handlers OR added in this feature's call-site sweep (T019 / T036).

| `admin_audit_log.action` | Source | Effect on `detection_events.disposition` |
|---|---|---|
| `detection_event_acknowledged` | US1 banner acknowledge handler | UPDATE → `banner_acknowledged` |
| `detection_event_dismissed` | US1 banner dismiss handler | UPDATE → `banner_dismissed` |
| `detection_event_auto_resolved` | Density-anomaly threshold-drop sweep (spec 004) | UPDATE → `auto_resolved` |
| `detection_event_resurface` | NEW — spec 022 FR-006 POST handler | No UPDATE (preserved alongside existing disposition) |

`admin_audit_log` row shape for spec-022 transitions:

```
action         = 'detection_event_<transition>'
session_id     = <session>
facilitator_id = <facilitator>                        -- spec 022 transitions; existing spec-001 column
target_id      = <detection_events.id>::text         -- stringified bigint
previous_value = NULL  (or previous disposition for ACK/DISMISS)
new_value      = NULL  (or new disposition for ACK/DISMISS)
timestamp      = NOW()
```

The disposition-timeline click-expand UI reads these rows via the §7 query in `research.md`.

## Class-mapping registry (process-scope, hardcoded)

`src/web_ui/detection_events.py::EVENT_CLASSES` is the source-of-truth dictionary mapping panel-class keys to display labels. Per `research.md §5` (unchanged by the amendment):

```python
EVENT_CLASSES: dict[str, dict[str, str]] = {
    "ai_question_opened":  {"label": "AI question opened"},
    "ai_exit_requested":   {"label": "AI exit requested"},
    "density_anomaly":     {"label": "Density anomaly"},
    "mode_recommendation": {"label": "Mode recommendation"},
    "mode_change":         {"label": "Mode change"},
}
```

Post-amendment the registry simplifies — no `source` / `predicate` fields are needed because the table stores `event_class` verbatim per row. The parity gate at `scripts/check_detection_taxonomy_parity.py` enforces key-set + label-string equality with `frontend/detection_event_taxonomy.js`. Adding a class requires both modules to be updated coordinately AND a spec amendment (Clarifications §3 — fixed taxonomy).

## Cross-instance broadcast envelope (Postgres LISTEN/NOTIFY — research §1)

Per `research.md §1` (unchanged by the amendment), cross-instance routing uses Postgres LISTEN/NOTIFY. The envelope payload now references the persisted row's id directly:

```json
{
  "kind": "appended" | "resurfaced",
  "event_id": 1037,
  "event_class": "ai_question_opened",
  "event_class_label": "AI question opened",
  "participant_id": "<participant>",
  "trigger_snippet": "...",                  // truncated server-side to 1000 chars before NOTIFY
  "trigger_snippet_truncated": false,
  "detector_score": 0.87,
  "turn_number": 14,
  "timestamp": "2026-05-11T14:32:01.234Z",
  "disposition": "pending"
}
```

Channel naming, payload size constraints, and connection management are unchanged from the original §1.

## V18 derived-artifact traceability (amended)

Post-amendment, `event_class` is no longer derived from source-row attributes — it is written verbatim to the `detection_events.event_class` column at INSERT time. The class-mapping registry maps `event_class` to `event_class_label` for display; both ship in every API/WS payload. The `disposition` column is denormalized but reviewers can walk back via the `admin_audit_log` transition rows (where each transition's `target_id` points to the `detection_events.id`). The traceability chain is: panel label → `event_class_label` → registry → `event_class` (canonical column value) AND panel disposition → `detection_events.disposition` column → `admin_audit_log` transition rows for the same `target_id` (full history).
