# Research: Human-Readable Audit Log Viewer

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Phase**: 0 (Outline & Research)
**Date**: 2026-05-08

This document resolves the unknowns surfaced during clarify and identifies best-practice patterns for the chosen technical approach. Each section follows the format: **Decision** / **Rationale** / **Alternatives considered**.

---

## §1 — Frontend module location: `frontend/*.js` vs `src/web_ui/static/*`

**Decision**: Ship the new frontend modules as UMD files under `frontend/`:
- `frontend/audit_labels.js`
- `frontend/time_format.js`
- `frontend/diff_engine.js`

The `DiffRenderer` React component lives inline in `frontend/app.jsx` (the single-file SPA per spec 011 FR-002).

**Rationale**: The spec drafted `src/web_ui/static/...` paths, but the project does not have a `src/web_ui/static/` directory. The frontend is served from `frontend/` as a CDN-loaded React SPA with no build toolchain (spec 011 FR-002). The established pattern for pure-logic frontend modules — set by spec 025 in 2026-05-07 and codified in the `frontend_polish_module_pattern` memory note — is UMD `.js` files at `frontend/*.js`, loaded via `<script>` tags ahead of `app.jsx` in `frontend/index.html`. Tests live under `tests/frontend/` and run in Node (no browser required) because each module exports cleanly under both `module.exports` (Node) and `window.X` (browser). The DiffRenderer component itself, being JSX, must live in `app.jsx` rather than a separate `.tsx` file because `type="text/babel"` script tags can only resolve same-document JSX without a bundler.

**Alternatives considered**:
- `src/web_ui/static/audit_labels.js` (per the spec's draft text). Rejected: the path doesn't exist; introducing it forks the frontend convention. Updated spec FRs at clarify time would have been preferable, but the path references in FR-006/FR-008/FR-009 are still in the original locations — the plan compensates by overriding the location in this research note. The spec's path strings remain accurate as conceptual placeholders ("paired backend Python + frontend JS"); only the literal directory differs.
- A new `src/web_ui/static/` directory with a build step. Rejected: contradicts spec 011 FR-002 ("Single-file React JSX (CDN-loaded, no build toolchain)"); a build step is a Phase 3+ concession listed under spec 011's deferred items, not in scope here.

**Spec note**: A subsequent fix-PR or spec-amendment can rewrite the literal path strings in spec 029's FR-006/FR-008/FR-009 (and the corresponding spec 011 FR-028 reference) to match the actual landed paths. Per Constitution §14.2 spec amendments accompany the implementation that introduces the discrepancy. Tracked as an implementation-time spec-update item.

---

## §2 — Diff library selection

**Decision**: `diff@5.2.0` (jsdiff), point-pinned with sha384 SRI integrity, loaded via CDN — mirroring the spec 011 SR-001 pattern. The library exposes `diffLines()`, `diffWords()`, `diffJson()`, and `structuredPatch()` from a single UMD bundle. License: BSD-3-Clause. Bundle size: ~30KB minified. The implementation point-pin lives in `frontend/index.html` and is also referenced in the inline Worker bootstrap in `frontend/diff_engine.js`. The wider `5.x` framing earlier in this section was the v0 selection criterion; the final pin landed at 5.2.0 during implementation. The `scripts/` parallel install was separately bumped to 5.2.2 to clear the jsdiff DoS advisory (PR #346); the SPA-side CDN pin stays at 5.2.0 until a coordinated upgrade refreshes the SRI hash.

**Rationale**: jsdiff is the de-facto JS Myers diff library (used by VSCode's git integration, GitHub's web review surface, Prettier). It supports the three modes the spec needs: line, word, and JSON-aware diff (`diffJson`). UMD-compatible — loads cleanly via `<script src="https://cdn.jsdelivr.net/npm/diff@5/dist/diff.min.js" integrity="sha384-..." crossorigin="anonymous">`. The library exposes a stable surface that the `frontend/diff_engine.js` module wraps with size-threshold dispatch (main thread / Web Worker / raw).

The Web Worker path uses an inline-blob worker pattern: at module init, `diff_engine.js` constructs a `Blob` containing the worker code (which `importScripts(diffLibraryURL)` and processes `postMessage` requests), then creates a `URL.createObjectURL(blob)` and a `Worker` from it. This sidesteps the no-build-toolchain constraint — no separate `diff-worker.js` file to ship and no CSP `worker-src` configuration churn (the inline blob URL is same-origin under default CSP). Size-threshold logic lives in pure `diff_engine.js`; the Worker bootstrap is a small helper inside the module.

**Alternatives considered**:
- `fast-myers-diff` (smaller, ~5KB, line-only). Rejected: no word-level mode (Q2 of clarify session locked in word-level toggle), no JSON-aware mode. We'd ship two libraries to cover the modes the spec requires.
- `diff-match-patch` (Google). Rejected: the library uses a different algorithm (Myers + post-processing semantic cleanup); the cleanup adds bytes for behavior the spec doesn't ask for, and license is Apache-2.0 (compatible but mixing isn't necessary).
- Hand-rolled Myers in `frontend/diff_engine.js`. Rejected: 25-line function cap (Constitution §6.10) makes a from-scratch Myers implementation hard to keep readable; jsdiff's well-tested implementation closes a correctness risk we don't need to absorb.
- Backend-rendered diffs returned via the API. Rejected: pushes UI-state decisions onto the server; loses the per-row word-level toggle responsiveness; FR-008 explicitly mounts the renderer client-side.

---

## §3 — Web Worker fallback when `Blob`/`createObjectURL` unavailable

**Decision**: Detect `typeof Worker === "undefined" || typeof Blob === "undefined"` at `diff_engine.js` init. When unavailable, the 50KB-500KB tier falls back to a chunked main-thread render with `requestIdleCallback` yielding between line groups. The >500KB tier still raw-displays. This preserves the size-threshold contract while accepting that legacy / restricted-CSP environments degrade gracefully.

**Rationale**: The spec's threshold semantics are framed as "MUST run in a Web Worker" (spec FR-008 + SC-011). Strict reading would mean any environment without Worker support fails the SC. A more useful interpretation: the threshold is a *budget* — it MUST NOT block the main thread for the full diff duration. Chunked yielding meets the budget without the Worker. We document the fallback behavior in the test plan and emit a `console.info` when fallback engages so operators can see the path. Note: per spec 011 SR-001 CSP, `worker-src` is not currently in the directive list — relying on `default-src 'self'` to permit blob: workers. If a tightened CSP is introduced later, the fallback path is already wired.

**Alternatives considered**:
- Mandatory Worker; throw on unavailable. Rejected: too brittle; one operator deploying behind an aggressive proxy that strips Worker support breaks the panel without recourse.
- Server-side diff rendering as fallback. Rejected: see §2 — adds an API surface for a corner case; preserves the worker-vs-server-vs-client decision tree at runtime, complicating the data path.

---

## §4 — Action-label parity gate implementation

**Decision**: `scripts/check_audit_label_parity.py` works as follows:

1. `import src.orchestrator.audit_labels` and read the `LABELS` attribute (a `dict[str, dict[str, Any]]`).
2. Read `frontend/audit_labels.js` as text. Parse the JS module's `LABELS = {...}` literal using a small Python state-machine parser (NOT a full JS parser dependency) that handles the subset the registry uses — string keys, string `label` values, optional `scrub_value: true` literal. Reject anything outside the subset with a clear error.
3. Compare key sets: every backend key MUST have a frontend mirror; backend-extra keys fail the build.
4. Compare `label` values: every backend label MUST equal the frontend mirror's label string.
5. Frontend is allowed to omit `scrub_value` (it's backend-only per FR-006).
6. Exit 0 on parity, exit 1 with a structured error naming the offending key on drift.

The parser refuses to handle JS comments, computed keys, spread syntax, or any form not in the `frontend_polish_module_pattern`'s established UMD shape. This keeps the script under 100 lines.

**Rationale**: Adding a real JS parser dependency (esprima, lark) for a registry-shape check is over-engineering. The frontend module is owned by this spec; we control the shape. A small state-machine parser that errors loudly on unexpected forms is sufficient, mirrors the simplicity of `scripts/check_time_format_parity.py` (next section), and stays within Constitution §6.10 reasoning constraints.

**Alternatives considered**:
- `node scripts/check_audit_label_parity.js` (Node-side parity). Rejected: introduces Node as a CI dependency for a check that's downstream of Python tests anyway; better to keep CI Python-only for backend-adjacent gates.
- JSON-encoded registry shared between modules. Rejected: the frontend would need to parse JSON at module-load time; loses the explicit module-export shape; the parity-check problem just moves to "did you regenerate the JSON?"
- AST parse via `esprima-python`. Rejected: ~3MB dependency for a 50-line registry check.

---

## §5 — Time-formatter parity gate implementation

**Decision**: `scripts/check_time_format_parity.py` runs both modules against a fixed list of timestamps and asserts equal output. The fixtures cover:
- Epoch `1970-01-01T00:00:00Z`
- DST transition (`2026-03-08T07:00:00Z` — US DST start; backend always renders UTC so the locale conversion is the test target)
- A microsecond-precise UTC instant
- A naive-datetime-rejected case (the formatter MUST require timezone-aware input)
- An invalid input (None / empty string) — both modules MUST raise / throw with an aligned error shape

The Python module is imported directly. The JS module is invoked via `node -e "console.log(require('./frontend/time_format.js').formatIso(<ts>))"` per fixture. Outputs are byte-equal-asserted.

**Rationale**: Direct invocation beats parsing the JS — the format string is short enough that semantic equality (string compare) is the right check. Node is available in CI for the pre-existing frontend-test path; this script piggybacks on it.

**Alternatives considered**:
- Pure Python parity check (parse the JS format-string literal). Rejected: backwards from how the format is computed; we'd be testing the format-string equality, not the output equality.
- A combined parity gate covering both audit_labels AND time_format. Rejected: failure modes are different (label parity vs. timestamp output equality); separate scripts give clearer error messages.

---

## §6 — Audit-log query: `log_repo.get_audit_log_page` shape

**Decision**: New function `get_audit_log_page(session_id: UUID, offset: int, limit: int, retention_cap_days: int | None) -> AuditLogPage` in `src/repositories/log_repo.py`. Signature returns a paginated decorated-row result:

```python
@dataclass
class AuditLogPage:
    rows: list[AuditLogRow]
    total_count: int
    next_offset: int | None  # None when no more pages

@dataclass
class AuditLogRow:
    id: UUID
    timestamp: datetime
    actor_id: UUID | None
    actor_display_name: str
    action: str
    action_label: str
    target_id: UUID | None
    target_display_name: str | None
    previous_value: str | None  # already replaced with "[scrubbed]" if scrub_value
    new_value: str | None       # already replaced with "[scrubbed]" if scrub_value
    summary: str | None
```

The function builds a single SQL query with two LEFT JOINs (actor and target), applies the retention WHERE clause when the cap is set, ORDERs by timestamp DESC, and runs a parallel `COUNT(*)` for pagination. Display names come from `participants.display_name`; null-actor (orchestrator system actions) is rendered as the configured system-actor label `"Orchestrator"` at the call site, not in SQL.

Scrubbing is applied at the call site after the row decoration: the function consults the registry (`audit_labels.LABELS[action].get("scrub_value", False)`) and substitutes `previous_value` / `new_value` with `"[scrubbed]"` before returning. This keeps SQL readable and concentrates the scrub policy in Python.

**Rationale**: One query + one count is simpler than a window-function query computing both. Two LEFT JOINs are well-indexed (`participants.id` is PK). Scrub-on-decoration ensures no raw value ever leaves the function — defense in depth for any future caller that bypasses the `web_ui/admin_audit.py` endpoint.

**Alternatives considered**:
- Window-function query computing rows + count in one round trip. Rejected: marginal latency win at our scale; harder to read; harder to test.
- Separate `get_audit_log_count(session_id, retention_cap_days)`. Rejected: every page load runs both; awkward call ergonomics; the pair-call is the natural unit.
- Scrubbing in SQL (`CASE WHEN action IN (...) THEN '[scrubbed]' ELSE previous_value END`). Rejected: the scrub list is in Python (the registry); duplicating it in SQL introduces drift.

---

## §7 — Role-filtered WS broadcast call site

**Decision**: Emit `audit_log_appended` from a new helper in `src/web_ui/events.py` invoked immediately after the `admin_audit_log` row INSERT. The helper:

1. Fetches the just-inserted row (or the function returns the inserted row's id + the caller passes back the decorated payload).
2. Decorates it via `log_repo` (display-name JOIN, label lookup, server-side scrub).
3. Calls `broadcast_to_session_roles(session_id, roles=["facilitator"], event="audit_log_appended", payload=decorated_row)`.

The audit-log INSERT call sites currently live in `src/repositories/log_repo.py:append_audit_event(...)` (and a few facilitator-action paths). Each call site that produces facilitator-visible audit content gets the broadcast helper called as a follow-up. To avoid scattered duplicate code, `append_audit_event` itself takes an optional `broadcast_session_id` parameter; when set, it triggers the broadcast helper after the INSERT commits. This is additive — existing callers that pass nothing get pre-feature behavior.

**Rationale**: Centralizing broadcast in `append_audit_event` means new call sites (future facilitator actions in spec 022, 024, etc.) get the broadcast for free by passing the session_id parameter. Concentrates the role-filter rule in one place. The `broadcast_to_session_roles` helper is an existing primitive (spec 011 SR-010), just newly invoked here.

**Alternatives considered**:
- LISTEN/NOTIFY: PostgreSQL LISTEN on `admin_audit_log_inserted` channel, NOTIFY in a trigger. Rejected: introduces a trigger surface and a listening side-process; latency unpredictable; hard to enforce role-filter from the DB layer. The synchronous in-process call is simpler and has predictable P95.
- Polling: a background loop watches `admin_audit_log` for new rows and broadcasts. Rejected: poll interval becomes the latency floor; misses the SC-002 ≤ 2s budget at high event rates.
- Broadcasting to all participants with per-recipient filtering. Rejected: explicitly closed off in clarify Q1 (Option B was the rejected redaction path).

---

## §8 — Sensitive-value scrubbing at WS payload

**Decision**: The same scrub-on-decoration pass that runs in `log_repo.get_audit_log_page` also runs in the broadcast helper before `broadcast_to_session_roles` is called. Because the broadcast goes only to facilitators (role-filter from §7), the scrub is technically defense-in-depth — but it MUST run anyway, because future role-list expansions (e.g., a new "auditor" role, or a misconfigured deployment) would otherwise leak content the FR-014 contract forbids.

**Rationale**: Two-layer defense. Role-filter is the primary protection; scrub-at-payload is the secondary. If the role-filter ever fails open (bug, config change, operator override), the scrub still applies and `[scrubbed]` ships rather than raw content. Aligns with §4.8 defense-in-depth and §4.9 secure-by-design.

**Alternatives considered**:
- Skip scrub when role-filtered. Rejected: tightly couples the security guarantees of two layers. If the role-filter is changed later (e.g., to add an audit-only viewer role), the scrub omission silently becomes a leak.
- Scrub at the SPA. Rejected: clarify Q3 explicitly moved scrubbing server-side; the client never sees raw values for `scrub_value=true` actions.

---

## §9 — Initial registry seed: which actions ship in v1?

**Decision**: Seed `LABELS` with the audit-action strings that exist in current Phase 1+2 code. From a grep of `append_audit_event(action=...)` call sites:

| Action string | Label | scrub_value |
|---|---|---|
| `add_participant` | "Facilitator added participant" | False |
| `approve_participant` | "Facilitator approved participant" | False |
| `reject_participant` | "Facilitator rejected participant" | False |
| `remove_participant` | "Facilitator removed participant" | False |
| `pause_loop` | "Facilitator paused the loop" | False |
| `resume_loop` | "Facilitator resumed the loop" | False |
| `start_loop` | "Facilitator started the loop" | False |
| `stop_loop` | "Facilitator stopped the loop" | False |
| `transfer_facilitator` | "Facilitator role transferred" | False |
| `set_routing_preference` | "Routing preference changed" | False |
| `set_budget` | "Budget changed" | False |
| `review_gate_approve` | "Review gate: draft approved" | False |
| `review_gate_reject` | "Review gate: draft rejected" | False |
| `review_gate_edit` | "Review gate: draft edited" | False |
| `review_gate_pause_scope_changed` | "Review-gate pause scope changed" | False |
| `rotate_token` | "Auth token rotated" | True |
| `revoke_token` | "Auth token revoked" | True |
| `cap_set` | "Session length cap changed" | False |
| `auto_pause_on_cap` | "Loop auto-paused (length cap reached)" | False |
| `manual_stop_during_conclude` | "Loop manually stopped during conclude phase" | False |
| `session_config_change` | "Session config changed" | False |

Two actions ship with `scrub_value=True`: `rotate_token` and `revoke_token`. Both involve auth-token material whose `previous_value` / `new_value` columns may contain hashed-but-still-sensitive token references that should not appear in the live viewer. Spec 010 debug-export remains the path for forensic retrieval of those values.

The list is the v1 seed; specs 022 / 024 / future specs add entries via the registry. The CI parity gate enforces frontend mirror coverage for every entry. Action strings already in the codebase that lack a registry entry will render `[unregistered: <raw>]` per FR-015 and emit a WARN log — a built-in registry-coverage report.

**Rationale**: Seed grounded in actual call sites prevents "we forgot half the actions" at integration time. The `scrub_value=True` choices are narrow (auth-token rotations only); broader scrubbing (e.g., session-config changes) is a backward-compatible future tightening per FR-014's "Tightening to per-field granularity remains a backward-compatible future option."

**Alternatives considered**:
- Empty seed; specs add as they need. Rejected: ships the panel with nothing labeled in v1; SC-001 fails ("MUST render with human-readable labels").
- Seed everything possible including future-spec actions. Rejected: registers actions that don't exist; the parity gate would need an emit-source check to differentiate "registered-but-unused" from "registered-and-used".

---

## §10 — `[unregistered: <raw>]` fallback + WARN log

**Decision**: When an audit row's `action` is not in the registry, the API response sets `action_label` to `f"[unregistered: {action}]"` and the orchestrator emits a WARN log entry: `audit_label_drift action={action} session_id={session_id}`. The frontend `audit_labels.js` mirror's `formatLabel(action)` helper applies the same fallback so WS-pushed rows render consistently.

**Rationale**: The CI parity gate prevents drift going forward, but pre-existing audit rows from sessions before a new action was registered may exist. The fallback ensures the panel never crashes on unknown data; the WARN log surfaces drift for operator triage. The WARN-not-ERROR level matches the orchestrator's existing pattern for low-impact log-time anomalies (e.g., `RoutingLogger.warn_unregistered_reason`).

**Alternatives considered**:
- Hide unregistered rows from the panel. Rejected: breaks audit completeness; operators would see "11 rows" when the underlying log has 12.
- Render the raw action string with no `[unregistered]` marker. Rejected: makes drift invisible; operators wouldn't know to update the registry.

---

## §11 — Display-name lookup for deleted participants

**Decision**: When a `LEFT JOIN` returns null `display_name` for an actor or target id, the API substitutes `f"<deleted-participant {actor_id[:8]}>"` (truncated UUID for readability) and sets a flag-style annotation on the response that the SPA renders with a "(deleted)" indicator next to the truncated ID. The full UUID is preserved in the response for forensic audit completeness.

**Rationale**: Edge case from the spec ("Deleted participant referenced as actor or target"). Truncated UUID gives operators something to copy/paste while keeping the panel readable. The "(deleted)" indicator distinguishes from the orchestrator-actor case.

**Alternatives considered**:
- Show the full UUID always for deleted participants. Rejected: clutters the table.
- Show "Deleted Participant" with no identifier. Rejected: loses forensic walkability — operators investigating a security incident may need to cross-reference the UUID with backup data.

---

## §12 — Filter-control badge counter behavior (FR-013)

**Decision**: The filter-control badge displays an integer count of WS-pushed audit events that arrived while a filter was active and didn't match. Counter resets on filter clear or filter change. Counter persists in `useState` only — no localStorage, no cross-page persistence.

**Rationale**: The badge is operationally useful (operators see "5 events hidden") without surfacing identifying metadata about the hidden events (just a count). Resetting on filter change matches expected UX — changing the filter is a fresh count.

**Alternatives considered**:
- Persistent counter across filter changes. Rejected: confusing UX; "5 hidden" loses meaning when the filter context changes.
- Show the full hidden-event list on click. Rejected: contradicts the filter — operators just chose to hide; surfacing them defeats the choice. If they want to see, they clear the filter.

---

## §13 — Tests for V14 perf budgets

**Decision**: V14 binding contracts:
1. Panel-load query latency: traced into `routing_log` with stage `audit_log_query`. Phase F Playwright e2e drives 1,000-row session and asserts P95 ≤ 500ms over 10 fetches.
2. WS push latency: traced via existing `routing_log` per-stage timing. Test drives an `add_participant` action and asserts the broadcast lands at the test client within 2s.
3. Diff renderer (≤50KB): Node-runnable test in `tests/frontend/test_diff_engine.js` measures `diffLines()` over a 50KB synthetic input; asserts the worker boundary is correctly chosen and the main-thread path completes within budget on CI hardware (CI hardware is the budget reference; performance is platform-relative).
4. Filter application: O(N) over loaded page; tested implicitly via interaction tests; not separately budgeted because the page size is bounded ≤ 500 (env var max).

**Rationale**: V14 is a binding rule — perf budgets must ship as enforceable contracts. Each budget gets a test that exercises the budget on representative input. CI-hardware caveat is honest about the platform-relative nature of frontend perf.

**Alternatives considered**:
- Budget instrumentation only without enforcement tests. Rejected: V14 explicitly requires "enforceable contracts"; observation-only doesn't meet the bar.
- Budget tests run in production-shaped hardware. Rejected: CI hardware is what we have; document the convention; revisit if production users observe regressions on faster/slower hardware.

---

## §14 — Architectural test for FR-020 (no parallel mappings)

**Decision**: `tests/test_029_architectural.py` does:
1. Walk the `src/orchestrator/` tree.
2. For each `.py` file, AST-parse and look for module-level `dict[str, str]` or `dict[str, dict]` assignments whose keys overlap with audit action strings (the seed list from §9).
3. If any overlap is found AND the module is not `audit_labels.py`, fail with a clear error naming the offending file.
4. Repeat for `frontend/` `.js` files (lightweight regex on `LABELS = {`-style declarations).

The test runs in CI on every PR; it's the FR-020 enforcement.

**Rationale**: Without the architectural test, future specs could re-add a parallel mapping (the exact drift FR-020 prevents). The test catches it at PR time, before merge.

**Alternatives considered**:
- Manual code-review enforcement only. Rejected: code review misses things; the test gives mechanical assurance.
- Lint plugin (ruff custom rule). Rejected: heavier-weight; ruff custom rules are project-specific configuration; a single pytest test is local + obvious.

---

## §15 — The shared-module-contracts.md doc shape (per FR-019)

**Decision**: `contracts/shared-module-contracts.md` contains:
- Module path table (action-label registry: backend + frontend; time formatter: backend + frontend; diff renderer: frontend-only)
- Public signature for each module (Python type hints + JS JSDoc-style annotations)
- DiffRenderer prop interface (`previousValue`, `newValue`, `format`)
- Threshold constants (≤50KB / 50KB-500KB / >500KB)
- Stability guarantee: "Specs 022 and 024 cite this document when amending. Breaking changes to these signatures require coordinating amendments to this document, the consumer specs, and the parity gates."

The doc is small (one page, < 200 lines) and lives in this spec's contracts/ directory so 022 / 024 amendments can cite a stable filesystem path.

**Rationale**: Per Q5 of clarify, this doc is the integration anchor. Its purpose is to give downstream specs a single citable artifact rather than five paths-and-signatures scattered through 029's spec.

**Alternatives considered**:
- Embed the contract content in spec.md. Rejected: spec.md is already long; contracts/ is the conventional location for inter-spec interfaces.
- Skip the doc; let downstream specs cite source files. Rejected: source files mutate; the contract doc records the intentional public surface independent of incidental implementation details.

---

## Outstanding from clarify (deferred, low impact)

- **English-only v1 localization**: confirmed default-acceptable; revisit at i18n trigger or first non-English deployment request. No research action.
- **Spec path strings (`src/web_ui/static/...`)**: noted in §1 as an implementation-time spec-update item. No research action; tracked in tasks.md when generated.

---

## Summary

All clarify-resolved decisions translated into research-grounded design choices. No NEEDS CLARIFICATION remains in the technical context. Constitution Check passes pre-design (already verified in plan.md); will re-verify post-design after data-model.md + contracts/ land.
