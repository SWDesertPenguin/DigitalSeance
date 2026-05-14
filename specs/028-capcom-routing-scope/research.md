# Research: CAPCOM-Like Routing Scope

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Phase**: 0 (Outline & Research)
**Date**: 2026-05-14

This document resolves the unknowns surfaced during the 2026-05-14 clarify session and identifies the best-practice patterns for the chosen technical approach. Each section follows the format: **Decision** / **Rationale** / **Alternatives considered**.

---

## §1 — Schema additions: TEXT + CHECK vs. PG ENUM

**Decision**: All new constrained columns ship as `TEXT NOT NULL DEFAULT ... CHECK (col IN (...))`. No PostgreSQL `ENUM` types. Specifically:
- `messages.kind TEXT NOT NULL DEFAULT 'utterance' CHECK (kind IN ('utterance', 'capcom_relay', 'capcom_query'))`
- `messages.visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'capcom_only'))`
- `participants.routing_preference` — existing column already accepts arbitrary TEXT (no CHECK), so the new value `'capcom'` requires no DDL change; only the application-side enum union is widened.

**Rationale**: Matches the established pattern (`alembic/versions/011_session_length_cap.py` adds `sessions.length_cap_kind TEXT NOT NULL DEFAULT 'none' CHECK (length_cap_kind IN ...)` — same shape). PG ENUM types complicate forward-only migration (per Constitution §FR-017): adding a value to an ENUM requires `ALTER TYPE ... ADD VALUE`, which cannot run inside a transaction in older PG versions and forks the migration shape. TEXT + CHECK supports both add-value and remove-value via a `DROP CONSTRAINT` + `ADD CONSTRAINT` pair within a single migration. The application-side `Literal["public", "capcom_only"]` annotation already enforces the type for handler code.

**Alternatives considered**:
- PG ENUM type for `visibility`. Rejected: forward-migration friction; no projected need to add ENUM values in v2 (a third visibility tier is not on the v1 roadmap).
- BOOLEAN `is_capcom_only` instead of a TEXT enum. Rejected: spec FR-001 frames visibility as an enum to allow future scopes (e.g., a `facilitator_only` value if scope expands to scratch — explicitly out of scope v1 but anticipated by `[v2 follow-up]` notes). A two-value enum is the principled shape; flipping to BOOLEAN later costs another migration.
- New column on `participants` for `is_capcom` flag. Rejected: redundant with `routing_preference='capcom'`; introduces a sync invariant.

---

## §2 — Migration packaging: single revision vs. split

**Decision**: One alembic migration revision (`024_capcom_routing_scope.py`) bundles all DDL changes:
1. `ALTER TABLE messages ADD COLUMN kind TEXT NOT NULL DEFAULT 'utterance' CHECK (kind IN ('utterance', 'capcom_relay', 'capcom_query'))`
2. `ALTER TABLE messages ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'capcom_only'))`
3. `ALTER TABLE sessions ADD COLUMN capcom_participant_id TEXT REFERENCES participants(id)` (nullable; deferred-FK pattern from `001_initial_schema.py:_add_facilitator_fk` not needed because `participants` exists at migration time)
4. `CREATE UNIQUE INDEX ux_participants_session_capcom ON participants(session_id) WHERE routing_preference = 'capcom'` — partial unique index enforcing single-CAPCOM-per-session
5. `CREATE INDEX idx_messages_visibility ON messages(session_id, visibility, turn_number DESC)` — supports the visibility-filter context-assembly query path

The migration ID is **024** (next sequential after 023; spec 015's circuit-breaker audit landed as 023). Per `feedback_parallel_merge_sequence_collisions`, this slot is reserved by drafting it into this branch. No other open spec branches currently target slot 024.

**Rationale**: A single revision keeps the CAPCOM data-model surface atomic — every column the spec references appears together, the unique index ships with the column it constrains, and the down-migration drops them in reverse without ordering puzzles. Per Constitution §FR-017 forward-only constraint, the migration commits at one transaction boundary; partial application leaves a coherent shape.

**Alternatives considered**:
- Split into three migrations (one per column). Rejected: forward-only constraint disallows reordering; the three changes have no independent rollback value; the index depends on the column existing in the same transaction anyway.
- Combine with spec 011 UI-side migrations. N/A — spec 011 owns no DB shape; UI is read-only against the orchestrator API.

---

## §3 — Visibility filter placement in the context-assembly pipeline

**Decision**: The visibility filter runs as the message-load step inside `ContextAssembler.assemble()` (`src/orchestrator/context.py`) — applied to the freshly-fetched `Message` list BEFORE `_add_messages` / `_add_history` see it. A new pure function `_filter_visibility(messages, participant, capcom_id) -> list[Message]` is the single chokepoint; the assembler reads `sessions.capcom_participant_id` once at assemble-start.

**Semantic clarification (2026-05-14 implementation refinement)**: The filter applies UNCONDITIONALLY to panel AI participants — even when `capcom_id` is `None` (i.e., no CAPCOM currently assigned). Panel AIs always receive `visibility='public'` rows only. This preserves FR-011's no-retroactive-promotion invariant: historical `capcom_only` content from a prior CAPCOM-active period stays invisible to panel AIs after disable. Pre-feature behaviour is preserved by the migration's `DEFAULT 'public'` — every legacy row migrates as public, so panel AIs see every legacy message unchanged.

**Rationale**: Placing the filter at the last context-assembly stage minimizes regression surface — every other prioritization, deferral, and roster stage runs against the unfiltered message universe (preserving accurate priority math), and the filter trims at the wire boundary. The architectural test (FR-019) becomes auditable because the filter is a single function call with a single entry point: any code path that bypasses it is a bug detectable by AST scan. Placing the filter EARLIER (during `_add_messages` priority math) would mean the priority budget already excludes invisible messages — that's wrong because a CAPCOM AI's larger view participates in priority math via the same code, and bifurcating priority by visibility would fork the assembler.

**Alternatives considered**:
- Filter at the SQL query (parameterize the message-fetch WHERE clause by participant + visibility). Rejected: forks the read path into per-participant queries, breaks the existing cached message-list pattern in `assemble`, complicates the architectural test (which would have to grep SQL not Python).
- Filter at the bridge dispatch boundary (after `_secure_content`). Rejected: trust-tier wrapping operates on raw content; filtering after wrapping risks leaking visibility metadata into the wrapped envelope. Filter before wrap, wrap the survivors.
- Two assemble paths (`_assemble_for_capcom` / `_assemble_for_panel`). Rejected: doubles the maintenance surface; introduces the bypass risk the architectural test is designed to eliminate.

---

## §4 — Architectural test for FR-019 (no bypass paths)

**Decision**: A pytest test `test_028_architectural.py::test_no_message_content_read_bypasses_visibility_filter` runs an AST scan over `src/`. The scan flags any `messages.content` access (column attribute or dict-key lookup) outside the allowlist:
1. `src/orchestrator/context.py` — the assembler (which IS the only legitimate dispatch path)
2. `src/repositories/message_repo.py` — the persistence read/write surface (raw row I/O; not dispatch)
3. `src/web_ui/admin_export.py` (spec 010 debug-export) — facilitator-only forensic surface; flagged as allowlisted because the export is explicitly visibility-aware per FR-024
4. Any file under `tests/` — test code is exempt

The scan looks for two AST patterns: `Attribute(value=Name(...), attr='content')` where the Name binds to a row from a `messages` query, and `Subscript(value=..., slice='content')` over a known row variable. The test fails CI with a structured error naming the offending file:line and the bypass shape. New legitimate consumers add themselves to the allowlist in the test file with a comment explaining why; the diff makes the allowlist expansion reviewable.

**Rationale**: A static-analysis gate at CI time is the cheapest enforcement mechanism for an architectural invariant. Runtime checks (e.g., a `MessageContentReader` ABC with a single implementation) impose abstraction overhead the codebase doesn't currently carry; grep-only checks miss subtleties like aliased imports. AST scanning is precise and bounded (the codebase has finite read sites; the allowlist is < 5 entries).

**Alternatives considered**:
- Runtime tainting (mark `content` reads with a token; assert the visibility filter consumed the token). Rejected: framework-level invasive; AST scan covers the same surface at zero runtime cost.
- Pure grep gate (`scripts/check_visibility_filter_bypass.py`). Rejected: too many false positives (`models.content`, `request.content`, `Path.content` all match the literal); AST disambiguates.
- Mypy plugin enforcing a tainted-type discipline. Rejected: over-engineered for one invariant; cost of plugin maintenance > cost of one AST test.

---

## §5 — Two-tier summarizer storage (spec 005 coordination)

**Implementation discovery (2026-05-14)**: Spec 005 does NOT use a separate `checkpoint_summaries` table — summaries persist as messages with `speaker_type='summary'` (see `src/repositories/message_repo.py::_SUMMARIES_SQL`). The drafted "discriminator column on `checkpoint_summaries`" approach therefore does not apply.

**Revised decision (Phase 7 scope)**: The two-tier summarizer reuses spec 028's existing `messages.visibility` column. When CAPCOM is assigned at a checkpoint:
- The summarizer emits TWO summary messages with `speaker_type='summary'`.
- The PANEL summary persists with `visibility='public'` and covers `visibility='public'` source rows only.
- The CAPCOM summary persists with `visibility='capcom_only'` and covers `visibility='public' OR visibility='capcom_only'` source rows.

Context assembly already filters by visibility (§3, §FR-006): panel AIs receive the `public` summary; the CAPCOM AI receives both summaries (panel + CAPCOM) and is expected to prefer the CAPCOM one. To enforce single-summary-per-checkpoint-per-scope, the summarizer code path checks for existing rows at the checkpoint turn before writing.

**No additional migration** is required for two-tier summarizer storage. The Phase 7 work is purely in `src/orchestrator/summarizer.py`.

**Rationale**: Reusing the existing `visibility` column avoids a second migration and aligns the summary partition with the underlying message partition — the same routing-time invariant covers both. The CAPCOM AI seeing both summaries is acceptable because the CAPCOM-summary subsumes the panel-summary (panel is a strict subset). A code-side discriminator preference (CAPCOM summary preferred when both exist) lives in `_add_summary`.

**Alternatives considered**:
- Introduce a new `checkpoint_summaries` table (the original drafted approach). Rejected: forks the storage shape from spec 005's existing pattern; adds a migration; requires a query path change.
- Visibility-bound summaries (the chosen revision). Selected: zero new schema, reuses the same filter, single-source-of-truth.
- Single summary row with discriminator metadata. Rejected: forces summarizer to emit a tuple-shaped row that doesn't match the message schema.

---

## §6 — Endpoint paths and authorization model

**Decision**: Three new facilitator-only endpoints follow the spec 002 participant-settings pattern (`/sessions/:session_id/...`):
- `POST /sessions/:session_id/capcom/assign` — body `{"participant_id": "..."}`; sets target's `routing_preference='capcom'` and `sessions.capcom_participant_id=<participant_id>` transactionally; emits `admin_audit_log action='capcom_assigned'`.
- `POST /sessions/:session_id/capcom/rotate` — body `{"new_participant_id": "..."}`; reverts outgoing CAPCOM's `routing_preference` to the value recorded in `admin_audit_log` at assignment time (default `'always'` if no prior record), sets incoming participant's `routing_preference='capcom'`, updates `sessions.capcom_participant_id`, emits `admin_audit_log action='capcom_rotated'` with both ids.
- `DELETE /sessions/:session_id/capcom` — reverts current CAPCOM's `routing_preference`, sets `sessions.capcom_participant_id=NULL`, emits `admin_audit_log action='capcom_disabled'`.

Authorization mirrors spec 010 §FR-2 — facilitator-only; uses the existing facilitator-resolver dependency. Master switch `SACP_CAPCOM_ENABLED` is checked at route mount; when `false`, none of the three routes is mounted (HTTP 404 from every caller).

**Rationale**: Path naming follows the existing `/sessions/:id/*` cluster (spec 002 §FR-016 cascade endpoints, spec 027 standby endpoints); verb pairing (POST assign/rotate, DELETE disable) is REST-idiomatic for create-update-delete on a singleton subresource. Mounting at the master-switch boundary is the pattern spec 029 uses for `SACP_AUDIT_VIEWER_ENABLED` and spec 022 uses for `SACP_DETECTION_HISTORY_ENABLED` — operators who haven't opted in see a clean 404 with no surface drift.

**Alternatives considered**:
- Single `PUT /sessions/:id/capcom` body `{"participant_id": "..." | null}` replacing all three. Rejected: conflates assign/rotate/disable into one verb; loses the audit-log differentiation; complicates the request body validation.
- Endpoints on `/participants/:id/capcom` (participant-scoped). Rejected: rotation is a two-participant action; session-scoped is the natural noun.

---

## §7 — WebSocket event shapes for CAPCOM lifecycle

**Decision**: Three new WS event types fire from the assign/rotate/disable endpoints, broadcast to ALL session subscribers (not role-filtered — all participants need to know visibility-routing has changed):
- `capcom_assigned` — payload `{session_id, capcom_participant_id, capcom_display_name, timestamp}`. Fires after the assign endpoint commits.
- `capcom_rotated` — payload `{session_id, previous_capcom_id, previous_capcom_display_name, new_capcom_id, new_capcom_display_name, timestamp}`. Fires after rotate commits.
- `capcom_disabled` — payload `{session_id, previous_capcom_id, previous_capcom_display_name, timestamp}`. Fires after disable commits.

Client-side reaction: the SPA refetches the participant roster (to update routing-scope badges), greys/un-greys the `capcom_only` message-composer toggle based on whether a CAPCOM is now active, and re-renders the transcript filter (any `capcom_only` history the local client cannot see remains hidden).

**Rationale**: Broadcast scope is "all session participants" because every participant's UI surface depends on the CAPCOM state — even non-facilitator humans need to know whether the privileged channel is available. Display name is included in the payload so clients don't need a separate roster refetch for the badge string update. This is the same pattern spec 027 standby uses for `participant_standby_changed`.

**Alternatives considered**:
- Role-filtered to facilitator only. Rejected: the human UI surfaces the visibility toggle which depends on CAPCOM-active state; panel AI clients (via the participant API) may need to know they should adjust prompt scaffolding.
- Single `capcom_state_changed` carrying a state-machine value. Rejected: loses the action attribution clarity; the three actions have meaningfully different audit semantics (rotation is a transfer, disable is a teardown).

---

## §8 — In-flight `capcom_query` attribution during rotation

**Decision**: Arrival-time attribution. The human's response to an in-flight `capcom_query` is attributed to the CAPCOM-of-record at response arrival time (the post-rotation CAPCOM B), not at query emission time (the pre-rotation CAPCOM A). Implementation: when a `capcom_only`-scoped message lands during context assembly, the assembler reads `sessions.capcom_participant_id` at message-arrival time — there is no `query_id` foreign-key chain that would bind the response to the original questioner. The audit trail captures both: the `capcom_query` row attributes to A (the speaker at emission), the human's `capcom_only` reply row attributes to whoever the human is, the next CAPCOM context-assembly cycle reads the reply through the current CAPCOM (B).

**Rationale**: Per spec FR-013 and the Session 2026-05-14 clarification — rotation transfers the entire privilege channel. Routing a response to a now-non-CAPCOM AI would leak privileged content to a participant who has lost the privilege. The audit trail makes the cross-rotation chain inspectable so operators can reconstruct intent (query attributed to A → rotation event → response attributed to B). This deviates from "the questioner gets the answer" intuition but preserves the security envelope.

**Alternatives considered**:
- Emission-time attribution (the answer goes to the questioner regardless of rotation). Rejected: directly violates the rotation privilege-transfer principle (spec assumption §rotation-not-accumulation).
- Block rotation while a `capcom_query` is in flight. Rejected: operators need rotation as an emergency tool; blocking would hand a denial-of-rotation vector to a misbehaving CAPCOM that emits a query and never accepts a reply.
- Migrate in-flight queries (clone the `capcom_query` row attribution to B on rotation). Rejected: rewrites historical attribution, which spec FR-010 explicitly forbids.

---

## §9 — Routing-log reason taxonomy extension

**Decision**: One new `routing_log.reason` value: `message_filtered_capcom_scope`. Per-turn, when the visibility filter excludes one or more messages from a participant's context, the assembler appends a `routing_log` row with `reason='message_filtered_capcom_scope'` carrying the exclusion count in a structured suffix (e.g., `reason='message_filtered_capcom_scope:excluded=7'`). This makes the partition's effect observable per turn without polluting the routing-log row schema.

**Rationale**: Reusing the existing `routing_log` row shape via a structured-suffix convention avoids a column addition. The detection taxonomy parity script (per `feedback_closeout_preflight_scripts`) will need the new reason value added to its allowlist. Operators inspecting routing-log for a session see the filter's effect alongside the standard routing decisions.

**Alternatives considered**:
- New table `visibility_filter_log`. Rejected: low information density per row; the existing `routing_log` row carries the necessary context (session, turn, participant).
- Structured JSON column on `routing_log`. Rejected: schema change for one new field; the suffix convention matches existing reason-string patterns elsewhere in routing_log.

---

## §10 — Frontend / spec 011 coordination strategy

**Decision**: Spec 011 amendments are deferred to implementation time per the `reminder_spec_011_amendments_at_impl_time` memory. Spec 028's `plan.md` enumerates the SPA changes (CAPCOM badge on participant card, visibility indicator on transcript messages, facilitator assignment/rotate/disable UI, human-side per-message visibility toggle), and `tasks.md` includes specific tasks for each — but the spec 011 FR text additions are NOT drafted here. At implementation time, the user is asked which 011 FR slots to use and what wording to drop in.

**Rationale**: Per the memory `reminder_spec_011_amendments_at_impl_time` and `feedback_synthesis_docs_local_first` — spec 011 is a high-visibility document with cross-cutting FR numbering. Drafting amendments here without explicit user approval is the recon-friendly mistake the rule guards against. The scaffold can describe the UI surface in spec 028's own plan + tasks without claiming spec 011 lines.

**Alternatives considered**:
- Draft the spec 011 amendments here. Rejected: violates the spec-011 reminder; introduces FR-numbering collision risk with parallel spec branches.
- Defer all UI work to a follow-up branch. Rejected: leaves spec 028 with no end-to-end demonstrable scenario; the implementation cannot satisfy SC-001..SC-005 without UI scaffolding.

---

## §11 — CAPCOM-side prompt scaffolding (spec 008 coordination)

**Decision**: Spec 008's prompt-tier text gains a CAPCOM addendum at implementation time. The addendum appears in the CAPCOM AI's system prompt when `routing_preference='capcom'` is detected at dispatch and reads (draft, settable at implementation):

> You are the CAPCOM for this session. The panel of AI participants sees only what you forward as `capcom_relay` messages plus their own direct emissions. Humans share a private channel with you. Curate the panel's view: when humans ask questions, decide whether to summarize for the panel or to ask the human a clarifying question via `capcom_query`. The panel sees your `capcom_relay` messages but does NOT see the underlying human messages.

No new prompt-tier values are introduced. The addendum is a conditional suffix to whatever tier the CAPCOM participant already runs. The exact wording is settled in the spec 028 implementation task list, NOT here.

**Rationale**: Spec 008's prompt-tier vocabulary is the canonical surface for trust-tier scaffolding; injecting a CAPCOM-specific prompt addendum without coordinating with the spec 008 maintainer risks drift. Drafting placeholder text at the research stage marks the work without claiming the final wording.

**Alternatives considered**:
- New prompt tier `capcom`. Rejected: spec 028 doesn't introduce a new trust tier (CAPCOM still runs at the participant's existing tier); a new tier value would imply trust-tier changes the spec doesn't require.
- No scaffolding (let operators construct CAPCOM prompts manually). Rejected: every CAPCOM-active deployment would need bespoke prompt work; the addendum is the lift that makes CAPCOM operate-out-of-the-box.

---

## §12 — Compression interaction (spec 026 coordination)

**Decision**: Spec 026 compression operates on a CAPCOM AI's overflow exactly the same as any other participant — pre-bridge, per-participant. The CAPCOM AI's compressed segment may contain `capcom_only` content (since the CAPCOM sees it); the trust-tier wrapping (spec 026 FR-012) marks the segment as derived from CAPCOM-private content via a new wrapping label `capcom_only_compressed`. The compressed segment is delivered ONLY to the CAPCOM's own provider — never cross-leaked into another participant's context (spec 026's per-participant delivery invariant is what makes this safe).

**Rationale**: Spec 026's pre-bridge per-participant compression model already enforces the cross-participant isolation invariant (Layer 6 closed-API skip, MIN-resolution on trust-tier). The CAPCOM case is a tagged variant; no new compression mechanism is required. The wrapping label addition is a one-line constant addition in spec 026's wrapper code.

**Alternatives considered**:
- Skip compression on `capcom_only` content. Rejected: the CAPCOM's overflow is the most likely to hit compression (their view is the largest); skipping leaves the partition functional only at small message volumes.
- Compress `capcom_only` content separately and never deliver to CAPCOM. Rejected: defeats the purpose of compression (preserving signal in overflow); the CAPCOM relies on the historical view to make relay decisions.

---

## §13 — Architectural test allowlist for `messages.content`

**Decision**: The FR-019 architectural test allowlists exactly these read sites for `messages.content`:
1. `src/orchestrator/context.py` — assembler (the legitimate dispatch path)
2. `src/repositories/message_repo.py` — DAO layer (raw row I/O, NOT dispatch)
3. `src/web_ui/admin_export.py` (spec 010 debug-export) — facilitator-only forensic surface; explicitly visibility-aware
4. `src/orchestrator/summarizer.py` (spec 005) — summarizer; visibility-aware per spec 028 FR-018
5. `src/security/density.py` (spec 004 §FR-020) — density-signal compute; pure-analytic, doesn't reach a participant's wire

Additions to this allowlist require a comment in `tests/test_028_architectural.py::ALLOWLIST` explaining the read site's purpose and confirming it does NOT route content to a participant without visibility filtering. The diff is the reviewable record.

**Rationale**: Five sites is small enough to be auditable in a single test file. Each entry carries an explicit reason; new entries fail CI unless the reviewer accepts the allowlist expansion. Allowlist drift is itself observable.

**Alternatives considered**:
- Strict zero-allowlist (every content read must route through `ContextAssembler`). Rejected: spec 005 summarizer is a legitimate non-dispatch reader; spec 010 debug-export is operator-authorized; spec 004 density is pure analytics. A blanket rule misses legitimate cases.
- Allowlist by module prefix (anything under `src/orchestrator/`). Rejected: too coarse; admits new orchestrator-side bypass paths without review.

---

## §14 — Concurrency model: rotation transaction vs. unique-index race

**Decision**: Rotation is a single SQL transaction:

```sql
BEGIN;
UPDATE participants SET routing_preference = <prior_value> WHERE id = <old_capcom>;
UPDATE participants SET routing_preference = 'capcom' WHERE id = <new_capcom>;
UPDATE sessions SET capcom_participant_id = <new_capcom> WHERE id = <session_id>;
INSERT INTO admin_audit_log (...) VALUES (..., 'capcom_rotated', ...);
COMMIT;
```

The unique partial index `ux_participants_session_capcom` does NOT trip on this sequence because the first UPDATE removes the old participant from the partial-index covered set BEFORE the second UPDATE adds the new participant. PostgreSQL evaluates UNIQUE constraints at statement boundary within the transaction; the intermediate state (two participants with `routing_preference='capcom'`) never exists because the UPDATEs are sequential within the same transaction.

The assignment-time `prior_value` is read from the `admin_audit_log` row for the participant's `capcom_assigned` event; if no such row exists (defensive default), `prior_value` falls back to `'always'`.

**Rationale**: Sequential UPDATE-then-UPDATE within a transaction is the standard PG pattern for swap operations under a partial unique index. The fallback to `'always'` matches the column's default and is the safe restore value.

**Alternatives considered**:
- DEFERRABLE INITIALLY DEFERRED on the unique index. Rejected: partial unique indexes do not support deferred constraint checking in PG 16; the sequential UPDATE pattern is the supported approach.
- Drop-and-recreate the partial index during rotation. Rejected: DDL inside the rotation transaction defeats the index's purpose under concurrent facilitator actions; a second facilitator could rotate in the gap.

---

## §15 — `tests/conftest.py` schema mirror update

**Decision**: Per `feedback_test_schema_mirror`, every column added by `024_capcom_routing_scope.py` is mirrored in `tests/conftest.py` raw DDL. Specifically:
- `messages.kind` and `messages.visibility` added to the messages CREATE TABLE literal.
- `sessions.capcom_participant_id` added to the sessions CREATE TABLE literal.
- The unique partial index `ux_participants_session_capcom` is added via a separate `CREATE UNIQUE INDEX` statement in the test fixture setup.
- `checkpoint_summaries.summary_scope` and `ux_checkpoint_summaries_scope` likewise mirrored.

The mirror update is a required task in the spec 028 implementation list; without it, the DB-bound tests on CI build a schema that doesn't match the migration, and the new columns/index are silently absent (only surfacing as test failures in surprising ways).

**Rationale**: This is a non-negotiable per the memory note. Conftest schema mirror divergence has shipped at least once before (the memory documents the failure mode) and the cost of catching the drift in CI rather than at-the-task level is low.

**Alternatives considered**:
- Drive the test schema from alembic at test-startup time. Rejected: alembic migrations require a real PG instance to apply; the test fixture is DB-skip-on-no-postgres and would regress.
