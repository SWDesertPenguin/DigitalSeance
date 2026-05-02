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
