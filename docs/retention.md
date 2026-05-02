# SACP Data Retention Policy

Authoritative listing of every persistent table and its retention behavior. This doc inventories all 15 persistent tables, their retention enforcement mechanism, and the GDPR Art. 17 erasure cascade.

The default policy is "indefinite — operator-driven", which means SACP itself never deletes the rows; the deploy operator runs a periodic purge if their compliance posture requires one. Tables with stronger defaults are called out below.

---

## 1. Per-table inventory

| Table | Retention policy | Enforcement |
|---|---|---|
| `sessions` | Indefinite until facilitator-driven session deletion | Cascade from `DELETE FROM sessions` (FK ON DELETE CASCADE on dependents) |
| `participants` | Indefinite until session deletion OR facilitator-issued reject | Hard-delete via reject; otherwise FK cascade from `sessions` |
| `messages` | Indefinite until session deletion | FK cascade from `sessions` |
| `branches` | Indefinite until session deletion | FK cascade from `sessions` |
| `routing_log` | Indefinite — `SACP_ROUTING_LOG_RETENTION_DAYS` (reserved) | Operator-driven purge job (not yet wired); FK cascade from `sessions` |
| `usage_log` | Indefinite — `SACP_USAGE_LOG_RETENTION_DAYS` (reserved) | Operator-driven purge job; FK cascade from `participants` |
| `convergence_log` | Indefinite until session deletion | FK cascade from `sessions` |
| `admin_audit_log` | Indefinite — `SACP_AUDIT_RETENTION_DAYS` reserved (default never-delete) | **Survives session deletion** — denormalized identifiers, no FK |
| `security_events` | Indefinite — `SACP_SECURITY_EVENTS_RETENTION_DAYS` (reserved) | Operator-driven purge job; FK cascade from `sessions` |
| `interrupt_queue` | Cleared after delivery (logical: `delivered_at IS NOT NULL`) | Operator-driven hard-delete or kept indefinitely; FK cascade from `sessions` |
| `review_gate_drafts` | Indefinite until session deletion | FK cascade from `sessions` |
| `invites` | Until expiry OR consumption (`uses >= max_uses`) | Logical retention via `expires_at`; FK cascade from `sessions` |
| `proposals` | Indefinite until session deletion | FK cascade from `sessions` |
| `votes` | Indefinite until proposal/session deletion | FK cascade from `proposals` → `sessions` |
| `summaries` | Indefinite until session deletion | FK cascade from `sessions` |

**Tables that survive session deletion**: `admin_audit_log` only. This is a deliberate carve-out — facilitator actions are subject to compliance review even after the session itself is purged, so the table holds denormalized `session_id` / `facilitator_id` strings rather than FK references.

---

## 2. Erasure-right (GDPR Art. 17)

Per-participant erasure cascade order (run inside one transaction):

1. `votes WHERE participant_id = $1`
2. `interrupt_queue WHERE participant_id = $1`
3. `usage_log WHERE participant_id = $1`
4. `messages WHERE speaker_id = $1`
5. `review_gate_drafts WHERE participant_id = $1`
6. `participants WHERE id = $1` (the row itself)
7. `admin_audit_log` rows are **retained** — Art. 17(3)(b) carve-out for compliance with legal obligations

Per-session erasure (drops the whole session): a single `DELETE FROM sessions WHERE id = $1` cascades all the above tables in a single transaction. `admin_audit_log` rows again survive.

Soft erasure (data minimization without row deletion): operator-defined column scrubbing for participant rows. Reserved for cases where session continuity is required but the participant requested anonymization.

---

## 3. Retention vs session deletion

Atomic-deletion contract: deleting a session must delete every row that references it, in one transaction, leaving no orphans — except `admin_audit_log`, which is explicitly preserved as the audit-survival pattern.

This is implemented two ways:
- **At schema level**: every operational table has FK `ON DELETE CASCADE` to `sessions(id)`. Deleting the session row implicitly deletes children.
- **At policy level**: `admin_audit_log` deliberately omits the FK and uses denormalized identifiers, so the row survives.

A schema-mirror CI gate catches drift between migrations and the test fixture DDL, so the FK shape stays consistent.

---

## 4. Derived data retention

- **Summaries** (`summaries` table): live as long as their parent session. Summarization is fire-and-forget; failed summary generation does not retry — the next checkpoint boundary produces a fresh one.
- **Embeddings** (`convergence_log.embedding`): live as long as the session. Stored as bytea; not separately purgeable.
- **Tier-text caches** (in-process LRU): per-process, evicted on restart; never persisted.

---

## 5. Backup retention

Backups are operator-managed and **separate from live-DB retention**:

- A purged row is gone from live DB, but may persist in backups until the operator's backup-rotation policy expires it.
- For Art. 17 erasure requests, the operator must either (a) tombstone the participant id in their backup index so a restore-and-redact procedure can replay the deletion, or (b) explicitly redact the row from any restored backup before bringing it online.
- Default backup retention: not opinionated by SACP. Operators are expected to define this in their deployment policy.

---

## 6. Retention monitoring & alerting

Operator-side metrics that signal "purge job stopped working":

- Row-count growth rate per logged table over rolling 7-day window. Sustained growth on a table that has a configured retention TTL (e.g., `routing_log`, `security_events`) indicates the purge job has silently failed.
- `pg_stat_user_tables.n_live_tup` for the operational logs over time. An order-of-magnitude jump after a deploy is a likely purge-failure fingerprint.
- Alert threshold: 7 consecutive days of zero rows deleted by the purge job when retention TTL is set, OR live-tuple count > 10× the rolling-30-day median.

These metrics are operator-observable; SACP itself does not emit retention-failure events today.

---

## 7. Retention env-var inventory

| Var | Status | Default | Effect |
|---|---|---|---|
| `SACP_AUDIT_RETENTION_DAYS` | Reserved | unset (never delete) | Purge job filters `admin_audit_log` rows older than N days |
| `SACP_SECURITY_EVENTS_RETENTION_DAYS` | Reserved | unset (never delete) | Purge job filters `security_events` rows older than N days |
| `SACP_USAGE_LOG_RETENTION_DAYS` | Reserved | unset (never delete) | Purge job filters `usage_log` rows older than N days |
| `SACP_ROUTING_LOG_RETENTION_DAYS` | Reserved | unset (never delete) | Purge job filters `routing_log` rows older than N days |

All four are reserved env vars — documented but not yet wired to a purge job. The purge job itself lands as a Phase 3+ deliverable; current deployments that need bounded retention run their own external purge query.

The 90-day default cited by 007 SC-009 (security_events) applies once the purge job is wired. Pre-wire, the effective retention is "never delete" regardless of the env var value — Section 1 reflects the as-of-Phase-1 reality.

---

## 8. Content vs. metadata retention

Retention granularity per row vs. column: in some compliance scenarios, a row's content (message body, prompt text, AI response) requires shorter retention than its metadata (timestamp, speaker_id, routing decision) which may be retained longer for analytics.

Phase 1 retention is **per-row**: when a `messages` row is deleted, both the body and the metadata go together. There is no built-in mechanism to scrub `messages.content` while keeping `messages.id`, `messages.speaker_id`, `messages.timestamp`, `messages.cost_usd`, `messages.complexity`. Operators that need this pattern (e.g., "de-identify after N days but keep the audit trail") implement it externally — a scheduled UPDATE that nulls or replaces sensitive columns while leaving the row.

Tables where content-vs-metadata distinction is relevant:

| Table | Content columns | Metadata columns | De-identification feasible? |
|---|---|---|---|
| `messages` | `content` | `id`, `branch_id`, `turn_number`, `speaker_id`, `timestamp`, `cost_usd`, `complexity` | Yes — operator UPDATE that nulls `content` |
| `routing_log` | `reason` (free-form), `error_message` | All routing fields + timings | Yes — operator UPDATE on free-form columns |
| `summaries` | `decisions`, `open_questions`, `key_positions`, `narrative` | `id`, `session_id`, `created_at`, `turn_window` | Yes — operator UPDATE on text columns |
| `security_events` | `findings` (JSON list of findings) | `session_id`, `speaker_id`, `turn_number`, `layer`, `risk_score`, `blocked`, `timestamp`, `layer_duration_ms` | Yes — operator UPDATE on `findings` |

Phase 3 trigger: any deployment with regulatory de-identification requirements (e.g., healthcare retention rules requiring de-identification at 6 years, full deletion at 7). Phase 1 deployments treat the row as the retention unit.

---

## 9. Retention test fixtures

Time-traveling tests verify that purge logic correctly identifies rows past their retention TTL. Phase 1 status:

- **Fixture pattern**: a pytest fixture seeds rows with `created_at` set to a past datetime (`datetime.now(UTC) - timedelta(days=N+1)`) where N is the retention TTL.
- **Test pattern**: invoke the purge query / job, then assert (a) rows older than the TTL are deleted, (b) rows within the TTL survive, (c) the parent table's row count matches expectations.
- **Coverage status**: NOT YET WIRED in Phase 1 — the purge jobs themselves do not exist (Section 7), so test fixtures are deferred until the jobs land. Phase 3 trigger: alongside the first purge-job implementation.
- **Anti-pattern**: never use `time.sleep` or wall-clock manipulation to age rows. Backdate `created_at` directly via INSERT — deterministic and fast.

Recommended location when wired: `tests/fixtures/retention/<table>_aged_seed.py` with a parameterized age delta.

---

## 10. Constitution + spec cross-references

The "indefinite by default + operator-driven purge with reserved env var" pattern originated in **001 §FR-019** for `admin_audit_log`. Tables that follow this pattern (the "001 §FR-019 retention pattern"):

| Table | Pattern source | Reserved env var |
|---|---|---|
| `admin_audit_log` | Canonical (001 §FR-019) | `SACP_AUDIT_RETENTION_DAYS` |
| `security_events` | Inherits (007 SC-009) | `SACP_SECURITY_EVENTS_RETENTION_DAYS` |
| `usage_log` | Inherits | `SACP_USAGE_LOG_RETENTION_DAYS` |
| `routing_log` | Inherits | `SACP_ROUTING_LOG_RETENTION_DAYS` |

Tables that intentionally DO NOT follow this pattern:

| Table | Why not |
|---|---|
| `convergence_log` | Session-scoped diagnostic data; retention beyond the session has no analytics value worth the storage cost |
| `messages` | Canonical transcript; treated as the unit-of-truth for the session — bound to session lifetime |
| `summaries` | Derived from messages; same lifecycle |
| `participants`, `branches`, `votes`, `proposals`, `interrupt_queue`, `review_gate_drafts`, `invites` | Operational state; tied to session lifetime via FK cascade |

Per-spec retention sections that reference this doc:

- 001 §FR-019 — admin_audit_log retention pattern (canonical)
- 001 §FR-020 — encryption-at-rest scope (Phase 1 covers `api_key_encrypted` only)
- 002 Compliance / Privacy → "Personal data inventory" (auth-token + bound_ip retention)
- 003 Compliance / Privacy → "Retention" (routing_log + usage_log)
- 007 SC-009 → security_events 90-day default (post-wire) + reserved env var
- 007 Compliance / Privacy → Art. 33 breach-notification timing record (security_events as canonical)
- 010 Compliance / Privacy → encryption-at-rest boundary + export-as-PII handling
- 011 Compliance / Privacy → CSP-report log retention
