# Research: Facilitator Scratch Window

**Branch**: `024-facilitator-scratch` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)

## §1 — Notes persistence shape

**Decision**: New table `facilitator_notes` with optional account FK and required session FK. Soft-delete semantics via `deleted_at`. Optimistic concurrency via `version` integer (incremented on every UPDATE; rejected at HTTP 409 on stale write per FR-004).

**Why**:
- Existing tables (`messages`, `admin_audit_log`, `security_events`) are append-only canonical surfaces (spec 001 §FR-008, V17 transcript canonicity). Notes are operator-private workspace state — neither canonical conversation nor audit ledger.
- A separate table makes the FR-001 architectural test (no path from notes to context-assembly) trivially provable: walk `src/orchestrator/context.py` + `src/prompts/` + the loop assembly path, assert no import of the notes repository.
- Soft-delete (vs hard) keeps the audit-log entry's reference durable and allows the spec 010 debug-export to enumerate deleted notes for forensic review (clarify Q5 + the FR-005 + FR-020 audit envelope).
- The `version` column is the spec 011 H-02 pattern repurposed: pure integer compare-and-swap is cheaper than ETag header machinery and is the simplest shape compatible with the autosave debounce.

**Alternatives rejected**:
- Single JSON column on `sessions`: violates V17 (mixes workspace state with canonical session config); breaks the FR-001 isolation guarantee (the context assembler reads `sessions`).
- Reuse `messages` with a new `speaker_type='facilitator_note'`: violates V17 (notes would be in the canonical transcript); the FR-001 architectural test becomes impossible to enforce.
- Separate notes DB / Redis: introduces a second persistence dependency; account-survives-archive guarantee (FR-016) becomes harder.

## §2 — Account-vs-session-scoped binding

**Decision**: `facilitator_notes.account_id` is nullable. The repository sets the FK at note-create time based on the current authenticated facilitator's account binding (looked up via `SessionStore` per spec 023 FR-016). NULL means session-scoped (deleted on archive per FR-017); non-NULL means account-scoped (survives archive per FR-016, optionally purged after `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE` per FR-018).

**Why**:
- Spec 023 ships the `SessionStore.account_id` field already (per its FR-016 + clarify Q9). The binding decision is a single SessionStore read at note-create time; no per-request walk through the spec 023 service layer.
- The `account_id NULL` branch is the fallback for `SACP_ACCOUNTS_ENABLED=false` deployments and for sessions joined via token-paste (legacy landing per spec 023 FR-018 / spec 011 amendment FR-030).
- FK to `accounts(id) ON DELETE SET NULL` ensures account deletion (spec 023 FR-012) does not orphan notes: the notes become session-scoped (FR-016 — clarify Q9 acceptance scenario for "Account is deleted while a session is in flight").

**Alternatives rejected**:
- Two separate tables (account-scoped vs session-scoped): doubles the architectural-test surface, doubles the migration, doubles the read-side query in the scratch panel.
- Account-only (require spec 023): rejected per spec text — session-scoped fallback is explicit deliverable.

## §3 — Scratch panel read-side query shape

**Decision**: Bounded `LEFT JOIN`s; three independent queries fired by the FR-002 endpoint, composed into one response payload. Notes from `facilitator_notes` filtered by `(session_id, account_id)` (account_id matches when scope is account-scoped; matched as `IS NULL` when session-scoped). Summaries from `messages WHERE speaker_type=''summary'' AND session_id=$1 ORDER BY turn_number DESC LIMIT 20 OFFSET $2`. Review-gate events from `admin_audit_log WHERE session_id=$1 AND action IN (''review_gate_approve'',''review_gate_reject'',''review_gate_edit'') ORDER BY timestamp DESC LIMIT 50` plus a LEFT JOIN to `participants` for display names.

**Why**:
- Three queries is cheaper than one giant UNION because the three result sets have different shapes and pagination contracts.
- 50-row review-gate cap is conservative; review-gate events are rarer than summary checkpoints (clarify-time intuition: typical sessions accumulate < 10 review-gate events).
- Offset pagination on summaries matches spec 029''s pattern (clarify Q8).

**Alternatives rejected**:
- WebSocket-only delivery: violates the "load panel and see history" UX; WS push handles new-rows-after-open via the FR-001 notes audit row going through spec 029''s `audit_log_appended` channel.
- Cursor pagination: per-session bounded count makes offset sufficient; matches spec 029 pattern.

## §4 — Promote-to-transcript dispatch path

**Decision**: New endpoint `POST /tools/facilitator/scratch/notes/<id>/promote` invokes the existing `inject_message` MCP tool''s underlying `_try_persist_injection` + `_broadcast_human_message` path (spec 006 `src/mcp_server/tools/participant.py`). The promote handler:
1. Loads the note.
2. Validates the active session is not archived (HTTP 409 per FR-006).
3. Runs the note content through `_validate_and_persist` security pipeline (spec 007 §FR-013).
4. On accept, emits the same `message_event` broadcast as a normal human turn.
5. Marks the note row `promoted_at` + `promoted_message_id`.
6. Writes one `admin_audit_log` row with `action=''facilitator_promoted_note''` carrying the prior note content (post-ScrubFilter).

**Why**:
- Reuses the existing path (FR-006 explicit). No new injection surface that could bypass spec 007''s security pipeline.
- The audit row + injection are sequenced inside one async function; on injection failure the audit row is NOT written (the audit trail records *successful* promotes, not attempts — failed attempts surface as the HTTP error to the SPA).
- The high-risk review gate (spec 007 FR-013 high-risk threshold) routes through the existing review-gate path; the SPA UI sees the same review-gate-staged WS event as any other human turn.

**Alternatives rejected**:
- Direct INSERT into `messages`: bypasses spec 007 ScrubFilter + spec 008 context-assembly invariants.
- Auto-retry on review-gate-staged: per FR-008 the promote does NOT bypass the security pipeline; review-gate-staged is a legitimate intermediate state the facilitator approves via the existing review-gate UI.

## §5 — Scratch panel UI surface and routing

**Decision**: Slide-over panel from the session header (NOT a route, NOT a modal). The route is `/session/:id/scratch` (registered for deep-linkability and SPA-state persistence on hard refresh) but the SPA renders the panel as a slide-over alongside the live transcript view. Three tabs (Notes / Summaries / Review Gate) backed by the same scratch payload from the FR-002 endpoint. Tab state is local (no URL-query-param routing — keeps the URL stable while the user tab-switches in the panel).

**Why**:
- Clarify Q1 explicit decision: tabs preserve live-transcript-context.
- Route-deep-linkability lets operators bookmark the scratch surface from a session URL.
- Spec 011 amendment FR-042 + FR-043 bind the affordance + route; FR-046 binds the spec 029 component reuse.

**Alternatives rejected**:
- Three separate slide-overs: clarify Q1 rejected.
- Modal (no route): blocks deep-linking; spec 029''s audit panel established the route-not-modal precedent.
- Full-page route: loses live-transcript-context the operator needs while scratch-thinking.

## §6 — Diff renderer reuse and architectural-test enforcement

**Decision**: Import the inline `DiffRenderer` component from `frontend/app.jsx` (spec 029 contracts/shared-module-contracts.md §3) and the locked threshold constants from `frontend/diff_engine.js` (§4). The scratch panel''s Review Gate tab renders each event as a row; clicking a row expands the diff via `<DiffRenderer previousValue={...} newValue={...} format="text" />`. Spec 024 ships ZERO diff-engine code; the FR-020 architectural test (spec 029) is extended to assert no spec 024 module declares Myers-diff helpers.

**Why**:
- Clarify Q6 + Q7 + Q12 explicit decision.
- Spec 029 already passed its `tests/test_029_architectural.py` enforcement; spec 024 inherits via the shared-module-contracts.md citation.

**Alternatives rejected**:
- Custom in-place diff renderer: duplicates spec 029 work; introduces parallel threshold constants the parity gate would flag.

## §7 — Audit-log envelope around promote-to-transcript

**Decision**: One audit row per promote click, written immediately after successful injection. `action=''facilitator_promoted_note''`, `actor_id=<facilitator participant id>`, `session_id=<session>`, `target_id=<note id>`, `previous_value=<prior note content post-ScrubFilter>`, `new_value=<resulting message id>`, `timestamp=<now>`. Re-promotion (clarify Q5) writes a SECOND audit row independently; both rows are durable. The new action MUST be added to the spec 029 action-label registry (both backend `src/orchestrator/audit_labels.py` and frontend `frontend/audit_labels.js`) with `scrub_value=False` (the prior note content is ALREADY ScrubFilter-processed at write time; double-scrubbing the registry-level pass would prevent operators from reading the historical content in the audit panel).

**Why**:
- One row per click matches spec 022''s disposition-transition pattern (one row per state change).
- Prior content + new message id together reconstruct the exact promote event for forensic review.
- ScrubFilter at write time (spec 007 §FR-012) means embedded secrets (API keys, tokens) are redacted BEFORE the row hits `admin_audit_log`; the audit panel surfaces the clean content.

**Alternatives rejected**:
- Audit row carrying note content + a separate row for the resulting message: doubles the storage; spec 029''s row-shape conventions accommodate previous + new in one row.
- `scrub_value=True` on the registered action: hides the historical content from the audit panel; defeats the FR-006 reconstructability requirement.

## §8 — Architectural test for "notes never reach context assembly"

**Decision**: New test `tests/test_024_architectural.py`. Two enforcement layers:

1. **Import scan**: walk `src/orchestrator/`, `src/prompts/`, `src/api_bridge/`, `src/operations/`; assert NO module imports `src.scratch.repository` (or any module that exposes the notes table). If the repo is renamed, this test breaks immediately.
2. **Runtime tracer**: a per-test fixture sets a `repo.find_notes` patched-in `asyncio.contextmanager` raising `AssertionError` on call. The fixture activates while the loop assembles context for a turn; if any code path resolves notes during assembly, the test fails.

The two layers catch (a) developer mistakes adding an import statically and (b) clever dynamic-import escapes.

**Alternatives rejected**:
- Import-only scan: misses dynamic-import escapes (e.g., a future module that resolves notes via `getattr(repos, ''notes_repo'')`).
- Runtime-only: misses dead code (an `import` line with no call site).

## §9 — Architectural test extension to spec 029 freshness

**Decision**: Extend `tests/test_029_architectural.py` (spec 029 FR-020) with a spec 024 assertion: walk `src/orchestrator/` and `frontend/` for any parallel definition of `MAIN_THREAD_BYTE_THRESHOLD` / `WORKER_BYTE_THRESHOLD` outside `frontend/diff_engine.js`. Any duplicate fails the build. This is the FR-020 architectural test contract — spec 024 amends the test rather than duplicating it.

**Why**:
- Spec 029''s contract document already names spec 024 as a consumer; the test extension is the enforcement.
- Single test file keeps the parity-gate logic in one place.

## §10 — Configuration env var shape (V16)

**Decision**: Three new vars per spec text (FR-022):

1. `SACP_SCRATCH_ENABLED`: boolean (`0` | `1`), default `0`. Master switch.
2. `SACP_SCRATCH_NOTE_MAX_KB`: positive int in `[1, 1024]`, default `64`. Per-note size cap; HTTP 413 above.
3. `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`: empty OR positive int in `[1, 36500]`, default empty (indefinite). Retention sweep for account-scoped notes.

All three add validator functions in `src/config/validators.py` registered in the `VALIDATORS` tuple, and corresponding sections in `docs/env-vars.md` with the six standard fields. The `check_env_vars.py` preflight enforces parity.

**Why**: spec text + V16 gate.

## §11 — Coordination with parallel lanes

- **Migration slot**: pre-allocated `019_facilitator_notes.py` per the spawn prompt''s "Pre-allocated slots for you: alembic revision `019_*`" line. Lane B (spec 026) reserves `020_*`; Lane C (spec 027) reserves `021_*`.
- **Spec 011 FR slot**: pre-allocated FR-042..FR-049 per the spawn prompt. Lane B reserves no new spec 011 FRs (it''s a Phase 3 backend refactor without UI surface) and Lane C reserves FR-052+ for the audit panel filter improvements (UI-only).
- **Audit-label registry**: spec 024 adds exactly one new action (`facilitator_promoted_note`) and four scratch-state actions (`facilitator_note_created`, `facilitator_note_updated`, `facilitator_note_deleted`, `facilitator_note_purged_retention`). All five MUST land in both `src/orchestrator/audit_labels.py` and `frontend/audit_labels.js` in the same commit per the parity gate.
