# Data Model: Human-Readable Audit Log Viewer

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Phase**: 1 (Design & Contracts)
**Date**: 2026-05-08

This spec is **read-only** on existing tables (FR-004). No schema changes ship in this spec. The data model below describes (a) the existing `admin_audit_log` source table this feature reads, (b) the read-side projections the API and WS event return, and (c) the in-memory registry / formatter / component shapes consumed by the frontend and CI parity gates.

---

## Source: existing `admin_audit_log` table (read-only)

Defined by spec 002 §FR-014. Schema reproduced here for reference; no migration in this spec.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID, PK | Audit row identity |
| `session_id` | UUID, FK to `sessions.id` | Bound to one session |
| `timestamp` | TIMESTAMPTZ, NOT NULL | UTC; index `(session_id, timestamp DESC)` |
| `actor_id` | UUID, NULLABLE | FK to `participants.id`; null for orchestrator-system actions |
| `action` | TEXT, NOT NULL | Canonical action string (e.g., `remove_participant`); the registry's primary key |
| `target_id` | UUID, NULLABLE | FK to `participants.id` for participant-targeted actions; null otherwise |
| `previous_value` | JSONB or TEXT, NULLABLE | Pre-edit content for actions with diffable values |
| `new_value` | JSONB or TEXT, NULLABLE | Post-edit content for actions with diffable values |
| `summary` | TEXT, NULLABLE | One-line human description for actions that don't fit actor-verb-target |

**Constraints applied at runtime by FR-004**:
- Application DB role has SELECT only on this table for the read path. INSERT remains via the orchestrator's audit-write helpers; UPDATE and DELETE are forbidden by `database/roles.sql` (Constitution §6.2 + §9 V9).
- The viewer query plus its display-name JOINs DO NOT lock rows beyond the default SELECT semantics.

---

## Read-side projection: `AuditLogRow`

Returned by `log_repo.get_audit_log_page(...)` and shipped in both the FR-001 endpoint response and the FR-010 WS event payload.

```python
@dataclass(frozen=True)
class AuditLogRow:
    id: UUID
    timestamp: datetime              # UTC, timezone-aware
    actor_id: UUID | None
    actor_display_name: str          # see §"Display name resolution" below
    action: str                      # raw action string from admin_audit_log.action
    action_label: str                # registry-derived; `[unregistered: <raw>]` fallback per FR-015
    target_id: UUID | None
    target_display_name: str | None  # null when target_id is null OR target is the session itself
    previous_value: str | None       # raw value, OR "[scrubbed]" when registry sets scrub_value=True
    new_value: str | None            # same scrubbing rule
    summary: str | None
```

### Display name resolution

| Case | actor_display_name |
|---|---|
| `actor_id` is null (orchestrator action) | `"Orchestrator"` (configurable label not env-varred at v1) |
| `actor_id` resolves via JOIN | `participants.display_name` |
| `actor_id` set but JOIN returns null (deleted participant) | `f"<deleted-participant {actor_id_short}>"` per [research.md §11](./research.md) |

`target_display_name` follows the same logic for `target_id`, with one extra case: when the action is session-scoped (e.g., `cap_set`, `session_config_change`), the field is null because the action targets the session itself, not a participant.

### Server-side scrubbing semantics

Per FR-014:
1. Look up the action in `LABELS` (the registry; see below).
2. If the entry's `scrub_value` is `True`, replace `previous_value` and `new_value` with the literal string `"[scrubbed]"` BEFORE returning the row.
3. The unscrubbed values never leave the `log_repo` function, so all upstream callers (HTTP endpoint, WS broadcast helper) transit only scrubbed content.

This is server-side defense (per [research.md §8](./research.md)); the SPA renders `previous_value` / `new_value` verbatim with no client-side decision.

---

## Read-side projection: `AuditLogPage`

```python
@dataclass(frozen=True)
class AuditLogPage:
    rows: list[AuditLogRow]
    total_count: int                 # total matching rows for pagination metadata
    next_offset: int | None          # offset for the next page; None when no more rows
```

Pagination is offset-based per FR-005. `total_count` is computed via a parallel `COUNT(*)` query with the same WHERE clause as the rows query (session_id + retention cap). `next_offset` is `None` when `offset + len(rows) >= total_count`.

---

## In-memory registry: `LABELS`

Defined in `src/orchestrator/audit_labels.py`; mirrored in `frontend/audit_labels.js` (without `scrub_value`).

```python
LABELS: dict[str, dict[str, Any]] = {
    "add_participant": {"label": "Facilitator added participant"},
    "approve_participant": {"label": "Facilitator approved participant"},
    "reject_participant": {"label": "Facilitator rejected participant"},
    "remove_participant": {"label": "Facilitator removed participant"},
    "pause_loop": {"label": "Facilitator paused the loop"},
    "resume_loop": {"label": "Facilitator resumed the loop"},
    "start_loop": {"label": "Facilitator started the loop"},
    "stop_loop": {"label": "Facilitator stopped the loop"},
    "transfer_facilitator": {"label": "Facilitator role transferred"},
    "set_routing_preference": {"label": "Routing preference changed"},
    "set_budget": {"label": "Budget changed"},
    "review_gate_approve": {"label": "Review gate: draft approved"},
    "review_gate_reject": {"label": "Review gate: draft rejected"},
    "review_gate_edit": {"label": "Review gate: draft edited"},
    "review_gate_pause_scope_changed": {"label": "Review-gate pause scope changed"},
    "rotate_token": {"label": "Auth token rotated", "scrub_value": True},
    "revoke_token": {"label": "Auth token revoked", "scrub_value": True},
    "cap_set": {"label": "Session length cap changed"},
    "auto_pause_on_cap": {"label": "Loop auto-paused (length cap reached)"},
    "manual_stop_during_conclude": {"label": "Loop manually stopped during conclude phase"},
    "session_config_change": {"label": "Session config changed"},
}
```

### Field rules

- `label`: required; English string per the deferred-but-default-accepted localization decision. The frontend mirror MUST contain the same string verbatim — CI parity gate enforces.
- `scrub_value`: optional; boolean; default `False` when omitted. Backend-only — the frontend mirror omits this field entirely. The CI parity gate ignores `scrub_value` parity (frontend is allowed to omit).

### Frontend mirror shape

```javascript
// frontend/audit_labels.js (UMD)
const LABELS = {
    "add_participant": { label: "Facilitator added participant" },
    "approve_participant": { label: "Facilitator approved participant" },
    // ... matching keys + label values; no scrub_value
};

function formatLabel(action) {
    const entry = LABELS[action];
    return entry ? entry.label : `[unregistered: ${action}]`;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { LABELS, formatLabel };
} else {
    window.AuditLabels = { LABELS, formatLabel };
}
```

The `formatLabel` helper lets WS-pushed rows render labels client-side when the SPA receives a row faster than the server-decorated payload (defense-in-depth — the server should always send `action_label`, but the helper is the safety net).

---

## Time-formatter API pair

### Backend: `src/orchestrator/time_format.py`

```python
def format_iso(dt: datetime) -> str:
    """UTC ISO-8601 with explicit Z marker.

    Raises ValueError if dt is naive (timezone-unaware).
    """

def format_iso_or_none(dt: datetime | None) -> str | None:
    """Wrapper for nullable timestamps."""
```

Output format: `2026-05-08T14:30:00.000Z` — millisecond precision (microseconds truncated to ms for parity with JS Date precision; this avoids a parity-gate failure mode where backend ships µs and frontend can't reproduce).

### Frontend: `frontend/time_format.js`

```javascript
function formatIso(timestamp) {
    // Input: ISO-8601 string OR Date object OR Unix epoch ms
    // Output: identical to backend format_iso for the same UTC instant
}

function formatLocale(timestamp) {
    // Browser locale-aware secondary display for the hover overlay
    // (uses Intl.DateTimeFormat with browser default locale)
}

function formatRelative(timestamp) {
    // "3 minutes ago" / "in 5 hours" — uses Intl.RelativeTimeFormat
}
```

Parity gate (`scripts/check_time_format_parity.py`) tests the `formatIso` output equality only. `formatLocale` and `formatRelative` are display-only conveniences and not parity-checked (browser locale variation is expected).

---

## DiffRenderer component shape

Frontend React component, lives in `frontend/app.jsx`.

### Props

```typescript
interface DiffRendererProps {
    previousValue: string | null;
    newValue: string | null;
    format?: "json" | "text" | "auto";  // default "auto"
}
```

### Rendering logic

1. If `previousValue == null && newValue != null` → render `newValue` alone with a "first set" indicator.
2. If `previousValue == "[scrubbed]" || newValue == "[scrubbed]"` → render both as `[scrubbed]` placeholders with no diff.
3. If `format == "auto"`, attempt `JSON.parse` on both values; if both parse, treat as `"json"`; else `"text"`.
4. Compute payload size: `previousValue.length + newValue.length`.
5. Apply size-threshold dispatch:
   - `≤ 50_000` chars: main-thread `diff.diffLines()` (or `diff.diffJson()` for JSON mode); render synchronously.
   - `50_000 < size ≤ 500_000`: dispatch to inline-blob Web Worker per [research.md §2](./research.md); render with "computing diff" placeholder until Worker returns.
   - `> 500_000`: render raw values side-by-side without a computed diff; show an info bar explaining the size limit.
6. Per-row word-level toggle: an in-row affordance ("show word-level diff") that, on click, lazily recomputes via `diff.diffWords()` and re-renders. State is per-row local; toggle state is not persisted.

### Constants (locked, no env-var override)

```javascript
// In frontend/diff_engine.js
const MAIN_THREAD_BYTE_THRESHOLD = 50_000;
const WORKER_BYTE_THRESHOLD = 500_000;
```

These constants are exported for use by spec 024's review-gate sub-panel per FR-019. Future spec consumers MUST import these constants rather than redefining them.

---

## WS event: `audit_log_appended`

Defined by FR-010 + clarify Q4 (Session 2026-05-08).

### Payload

Identical to one `AuditLogRow` per the read-side projection above. No additional envelope fields (the WS layer adds its own envelope per the existing pattern in `src/web_ui/events.py`).

### Delivery

- Broadcast scope: `roles=["facilitator"]` only via `broadcast_to_session_roles(session_id, ...)` per clarify Q1.
- Latency: P95 ≤ 2s from `admin_audit_log` INSERT to facilitator-client render.
- Deduplication: SPA uses `id` to de-duplicate against in-flight HTTP refetches.
- Order: not guaranteed — clients sort by `timestamp DESC` on render. The HTTP endpoint and WS path may interleave; `id` + `timestamp` together yield a stable order.

---

## Validation rules captured

- **FR-001 / FR-002 / FR-003**: endpoint validation lives at the FastAPI layer. Test the auth boundary (facilitator-only HTTP 403 for non-facilitators), the session-binding boundary (HTTP 403 when session_id doesn't match the caller's session), and the master-switch boundary (HTTP 404 when `SACP_AUDIT_VIEWER_ENABLED=false`).
- **FR-005**: pagination metadata MUST include `next_offset` and `total_count`.
- **FR-006**: registry shape `dict[str, dict[str, Any]]` with `label: str` required, `scrub_value: bool` optional. CI parity gate enforces.
- **FR-009**: time-formatter parity. CI parity gate enforces.
- **FR-014**: server-side scrubbing in `log_repo.get_audit_log_page` AND in the WS broadcast helper (defense in depth).
- **FR-016**: retention cap applied via `WHERE timestamp >= NOW() - INTERVAL` clause.
- **FR-017**: three new env vars require validators in `src/config/validators.py` AND `docs/env-vars.md` sections BEFORE `/speckit.tasks` (V16 gate).
- **FR-020**: architectural test enforces no parallel action-to-label mapping outside `src/orchestrator/audit_labels.py`.

---

## Entities NOT introduced

For traceability, this spec deliberately introduces **no** new persistent entities:
- No new tables.
- No new columns on existing tables.
- No new foreign keys.
- No new indexes (the existing `(session_id, timestamp DESC)` index on `admin_audit_log` is sufficient — verify presence at task time and add a migration only if missing).

Pure read-side surface + paired modules + WS event reuse.
