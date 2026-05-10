# Contract: Shared Module Contracts (FR-019 anchor)

**Spec**: [../spec.md](../spec.md) §FR-019 / FR-020 / FR-006 / FR-008 / FR-009
**Plan**: [../plan.md](../plan.md)
**Status**: Phase 1 contract draft — citable artifact for spec 022 / 024 amendments

This document is the **integration anchor** referenced by spec 029 FR-019. It pins the public surface of the action-label registry, time formatter, and diff renderer modules so downstream specs (022, 024, and any future audit-adjacent specs) can plan against a stable contract without coordinating mid-development.

**Stability guarantee.** Breaking changes to any signature in this document require coordinating amendments to (a) this document, (b) every consuming spec, (c) the parity gates (`scripts/check_audit_label_parity.py`, `scripts/check_time_format_parity.py`), and (d) the architectural test (`tests/test_029_architectural.py`). Additive changes (new optional fields, new helpers) do NOT break the contract.

---

## §1 — Action-label registry

### Backend module

**Path:** `src/orchestrator/audit_labels.py`

**Public surface:**

```python
LABELS: dict[str, dict[str, Any]]
"""Registry mapping audit action strings to entries.

Each entry has:
- `label`: str (required) — the human-readable English label
- `scrub_value`: bool (optional, default False) — whether the FR-001 endpoint
  and FR-010 broadcast helper should replace previous_value/new_value with
  the literal string "[scrubbed]" before transmission.
"""

def format_label(action: str) -> str:
    """Return the registered label, or `[unregistered: <action>]` fallback.

    Emits a WARN log on the unregistered path per FR-015.
    """

def is_scrub_value(action: str) -> bool:
    """Return True if the action's registry entry has scrub_value=True; False otherwise."""
```

**Stability constraints:**
- The `LABELS` dict's value type is fixed to `dict[str, Any]` to allow additive flag fields.
- `format_label` and `is_scrub_value` are the only public helpers — direct callers MUST NOT iterate `LABELS` from outside this module unless they are the parity gate or the architectural test.
- Adding new actions to `LABELS` is additive and does not break the contract.
- Removing an action from `LABELS` is breaking — every downstream consumer depending on that label must update.

### Frontend module

**Path:** `frontend/audit_labels.js`

**Public surface (UMD):**

```javascript
const LABELS = { /* mirrors backend keys + label fields; no scrub_value */ };

function formatLabel(action) {
    // Returns the registered label string, or `[unregistered: ${action}]` fallback.
    // Does not log (browser console.warn would spam at the volume of unregistered events).
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { LABELS, formatLabel };
} else {
    window.AuditLabels = { LABELS, formatLabel };
}
```

**Stability constraints:**
- Frontend `LABELS` MUST contain every key in backend `LABELS`, with matching `label` strings (CI parity gate enforces).
- Frontend MUST NOT contain any key not in backend `LABELS`.
- The `formatLabel` helper is the sole rendering entry point; consumers MUST NOT read `LABELS[action].label` directly to get the same fallback semantics.

---

## §2 — Time formatter

### Backend module

**Path:** `src/orchestrator/time_format.py`

**Public surface:**

```python
def format_iso(dt: datetime) -> str:
    """UTC ISO-8601 with explicit Z marker, millisecond precision.

    Example output: "2026-05-08T14:30:00.000Z"

    Raises ValueError if dt is naive (timezone-unaware).
    """

def format_iso_or_none(dt: datetime | None) -> str | None:
    """Wrapper for nullable timestamps."""
```

**Stability constraints:**
- Output format is fixed: `YYYY-MM-DDTHH:MM:SS.sssZ` — millisecond precision, explicit `Z` timezone, no offset variants.
- Naive-datetime input is rejected at the API boundary (forces callers to pass timezone-aware values).
- Microsecond precision is intentionally truncated to milliseconds for parity with JS Date precision.

### Frontend module

**Path:** `frontend/time_format.js`

**Public surface (UMD):**

```javascript
function formatIso(timestamp) {
    // Input: ISO-8601 string OR Date object OR Unix epoch ms
    // Output: identical to backend format_iso for the same UTC instant
}

function formatLocale(timestamp) {
    // Browser locale-aware secondary display; uses Intl.DateTimeFormat
    // Used by the hover overlay; NOT parity-gated.
}

function formatRelative(timestamp) {
    // "3 minutes ago" / "in 5 hours"; uses Intl.RelativeTimeFormat
    // NOT parity-gated.
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { formatIso, formatLocale, formatRelative };
} else {
    window.TimeFormat = { formatIso, formatLocale, formatRelative };
}
```

**Stability constraints:**
- `formatIso` output MUST byte-equal `format_iso(dt)` for the same UTC instant. CI parity gate enforces.
- `formatLocale` and `formatRelative` are display-only helpers; their output may vary across browsers (locale, RTL handling) and is intentionally not parity-checked.
- All three helpers accept the union input type for ergonomic call sites — callers may pass an ISO string from an API response, a `Date` object from a WS event payload, or a raw epoch millisecond integer.

---

## §3 — DiffRenderer component + diff engine

### React component

**Path:** `frontend/app.jsx` (inline component within the SPA per spec 011 FR-002)

**Public props:**

```typescript
interface DiffRendererProps {
    previousValue: string | null;
    newValue: string | null;
    format?: "json" | "text" | "auto";  // default "auto"
}
```

**Behavior contract:**
- `previousValue == null && newValue != null` → render `newValue` alone with a "first set" indicator.
- Either value `=== "[scrubbed]"` → render both as `[scrubbed]` placeholders, no diff computation.
- `format == "auto"` → attempt JSON parse on both; if both succeed, treat as `"json"`; else `"text"`.
- Apply the size thresholds from §4 below.
- Default mode: line-by-line Myers diff. Per-row word-level toggle is a UI control inside the expanded row that, on click, lazily recomputes the diff at word granularity (state per-row local; not persisted).

### Pure-logic engine

**Path:** `frontend/diff_engine.js`

**Public surface (UMD):**

```javascript
const MAIN_THREAD_BYTE_THRESHOLD = 50_000;
const WORKER_BYTE_THRESHOLD = 500_000;

function chooseDiffMode(byteSize) {
    // Returns "main" | "worker" | "raw" based on the threshold constants
}

function diffLinesSync(previousValue, newValue, format) {
    // Synchronous line-by-line diff via jsdiff; called on the main thread
    // for size <= MAIN_THREAD_BYTE_THRESHOLD
}

function diffWordsSync(previousValue, newValue) {
    // Synchronous word-level diff via jsdiff; called lazily on toggle click
}

async function diffLinesViaWorker(previousValue, newValue, format) {
    // Inline-blob Worker bootstrap; resolves with the diff result
    // Falls back to chunked-yield main-thread render when Worker is unavailable
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        MAIN_THREAD_BYTE_THRESHOLD,
        WORKER_BYTE_THRESHOLD,
        chooseDiffMode,
        diffLinesSync,
        diffWordsSync,
        diffLinesViaWorker,
    };
} else {
    window.DiffEngine = { /* same surface */ };
}
```

**Stability constraints:**
- Threshold constants are LOCKED — no per-call override, no env-var tuning. Spec 024 FR-014 inherits these constants by importing.
- Future threshold changes require coordinating updates across (a) this contract document, (b) `frontend/diff_engine.js`, (c) spec 029 FR-008's spec text, (d) spec 024 FR-014's spec text.

---

## §4 — Size thresholds (locked module constants)

| Range (chars) | Mode | Notes |
|---|---|---|
| ≤ 50,000 | Main thread sync | P95 ≤ 100ms render budget |
| 50,001 – 500,000 | Inline-blob Web Worker | "computing diff" placeholder until Worker returns |
| > 500,000 | Raw display, no diff | Info bar explaining the size limit |

These thresholds are ONE definition consumed by:
- `frontend/diff_engine.js` (the source of truth)
- Spec 029 FR-008 (cross-reference)
- Spec 024 FR-014 (cross-reference)

Any future spec proposing a different threshold MUST update this contract document and propagate to all consumers in a coordinated PR.

---

## §5 — Parity gates

### Action-label parity (`scripts/check_audit_label_parity.py`)

**Required CI step.** Fails the build with a clear error naming the offending key when:
- Backend `LABELS` has a key not present in frontend `LABELS`
- Frontend `LABELS` has a key not present in backend `LABELS`
- A key's `label` string differs between backend and frontend

Backend-only `scrub_value` flags are NOT parity-checked (frontend mirror omits the field per FR-006 design).

### Time-formatter parity (`scripts/check_time_format_parity.py`)

**Required CI step.** Runs both modules against a fixed list of timestamp fixtures (epoch, DST transition, microsecond-precision, naive-rejection, invalid-input). Asserts byte-equal output from `format_iso` (Python) and `formatIso` (JS Node-invoked).

`formatLocale` and `formatRelative` are NOT parity-checked.

---

## §6 — Architectural test (FR-020)

**Path:** `tests/test_029_architectural.py`

Walks `src/orchestrator/` and `frontend/` for parallel action-to-label mappings. Fails the build when any module other than `src/orchestrator/audit_labels.py` (Python) or `frontend/audit_labels.js` (JS) declares a `dict` / `object` whose keys overlap with the registered audit action strings.

This is the FR-020 enforcement: no spec outside 029 may reimplement the registry.

---

## §7 — Consumer expectations for downstream specs

When spec 022 (detection-event-history) and spec 024 (facilitator-scratch / review-gate sub-panel) reach implementation:

### Spec 022's expected amendment shape

Spec 022's amendment FR(s) MUST cite this document and:
- Import `format_label`, `formatLabel` from the action-label registry for any audit-adjacent labels surfaced in the detection-event panel.
- Import `format_iso`, `formatIso` from the time formatter for timestamp rendering.
- Bind the `audit_log_appended` WS handler pattern (role-filter, decorated payload) when 022 introduces its own `detection_event` broadcast.
- NOT reimplement any of these helpers inline.

### Spec 024's expected amendment shape

Spec 024's amendment FR(s) MUST cite this document and:
- Use the `DiffRenderer` React component from `frontend/app.jsx` for the review-gate diff sub-panel.
- Use the threshold constants from `frontend/diff_engine.js` (no parallel constants in spec 024's code).
- NOT reimplement Myers diff helpers; `diff_engine.js` is the only diff source.

### General consumer rules

- New actions added by a downstream spec MUST add a corresponding `LABELS` entry to `src/orchestrator/audit_labels.py` AND `frontend/audit_labels.js` in the same PR. The CI parity gate enforces.
- New `scrub_value=True` actions MUST justify the choice in the amending spec's clarifications.
- Performance budgets for new audit-adjacent surfaces MAY reference these threshold constants but MUST NOT redefine them.

---

## Change log for this document

| Date | Change | Reason |
|---|---|---|
| 2026-05-08 | Initial draft | Phase 1 of spec 029 plan |
| 2026-05-09 | Verified against landed signatures (T044). No divergence — every cited path exists, every public symbol matches the documented surface, threshold constants pinned to 50,000 / 500,000. The architectural test (`tests/test_029_architectural.py`) and freshness test (`tests/test_029_contract_freshness.py`) enforce this going forward. | T044 closure during US4 implementation |

Future amendments to this contract MUST add a row here citing the amending PR and the consumer specs reviewed.
