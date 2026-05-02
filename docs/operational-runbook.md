# SACP Operational Runbook

Synthesis of every other doc in this directory, organized by what an operator actually does in the field.

This document targets a deploy operator with database access and familiarity with the codebase. End-user / facilitator workflows live elsewhere.

---

## 1. Deploy procedures

### 1.1 Prerequisites

- Postgres 16+ (the orchestrator uses asyncpg + `pg_advisory_lock`).
- Python 3.14.4 (per Constitution §6.8 slim-bookworm).
- Container runtime if deploying via the project's Dockerfile.

### 1.2 Pre-flight

```bash
# Verify all SACP_* env vars validate before starting
python -m src.run_apps --validate-config-only
```

Exit 0 = ready to deploy. Exit 1 = fix the listed vars before going further.

### 1.3 Database migration

```bash
alembic upgrade head
```

Migrations are forward-only; the `downgrade()` body is `pass` for every migration from the codification point onward. If a deploy must roll back, restore from backup rather than running a downgrade.

A schema-mirror CI gate catches drift between alembic migrations and the test fixture DDL, so a green CI pipeline guarantees the DDL the tests exercise matches the live schema.

### 1.4 Application start

```bash
python -m src.run_apps
```

Validation runs once more before the orchestrator starts — any failure exits non-zero before binding any port.

Boot sequence: env-var validation → DB pool init → encryption-key verify → alembic check (logged, not enforced) → port bind → ready.

### 1.5 Smoke checks

- `/health` (HTTP, MCP server) returns 200.
- `/ws/sessions/<id>` accepts a WS connection from a logged-in cookie and emits `state_snapshot` within 2 s.
- `routing_log` accumulates rows when a turn fires; per-stage timing columns (`route_ms` / `assemble_ms` / `dispatch_ms` / `persist_ms`) are populated on success-path rows.

### 1.6 Encryption at transit

Production deployments MUST set `sslmode=require` (or stricter — `verify-full` if the operator manages the CA chain) on the asyncpg connection string. Example:

```bash
SACP_DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
```

LAN / dev deployments MAY use `sslmode=disable` — document in the deployment readme.

The orchestrator does NOT enforce `sslmode=require` at startup; operator-controlled. See spec 001 Operations section for the Phase 3 trigger to validate at startup.

---

## 2. Backup / restore

### 2.1 Cadence

SACP does not opinionate on backup cadence — operator policy applies. The relevant tables are all in the same logical Postgres database; a single `pg_dump` captures everything.

Recommended floor: nightly logical backup + WAL streaming for PITR.

### 2.2 Restore-validation drill

A drill the operator should run quarterly:

1. Restore latest backup to a non-production environment.
2. Run `python -m src.run_apps --validate-config-only` against the restored DB (no port bind, just config + connectivity).
3. Connect to the orchestrator with a known facilitator token and verify a `state_snapshot` event arrives.
4. Compare `admin_audit_log` row count between live and restored; any drift flagged as backup-policy issue.

### 2.3 Erasure-aware restore

If a participant exercised Art. 17 erasure between the backup and the restore, the restored DB will hold their data again. Operator must either:

- Tombstone the erased participant ids in a side index, replay the deletion script after restore.
- OR redact the rows manually before bringing the restored DB online.

### 2.4 Encryption boundary

Encrypted columns (`api_key_encrypted`) restore as ciphertext. They remain decryptable only with the same `SACP_ENCRYPTION_KEY` the backup was taken under. If the key has rotated since (see § 3), restoration of pre-rotation rows requires the prior key.

Backup-at-rest encryption is operator-controlled and SHOULD use a key separate from `SACP_ENCRYPTION_KEY`. The encryption-key chain becomes:

- `SACP_ENCRYPTION_KEY` — Fernet column-level for `api_key_encrypted`
- Operator's backup-encryption key — pgBackRest / wal-e / native cloud snapshot encryption
- Operator's transport key — TLS for streaming backups to off-site storage

Compromise of any one key SHOULD NOT cascade to the others; this is the operator's deployment-policy boundary.

### 2.5 Operator-driven retention purge (pre-Phase-3)

The reserved retention env vars (`SACP_AUDIT_RETENTION_DAYS`, `SACP_SECURITY_EVENTS_RETENTION_DAYS`, `SACP_USAGE_LOG_RETENTION_DAYS`, `SACP_ROUTING_LOG_RETENTION_DAYS`) are not yet wired to a purge job. Operators with hard-cap retention requirements run an external query, e.g.:

```sql
-- Example: purge admin_audit_log rows older than 365 days
DELETE FROM admin_audit_log WHERE created_at < NOW() - INTERVAL '365 days';
```

Schedule via cron / pg_cron / operator's scheduling stack. Per `docs/retention.md` §6, monitor row-count growth rate to confirm the purge is running.

### 2.6 Restore-from-old-backup edge case

If a backup was taken at schema version V_old and current code expects V_new (forward-only migrations per 001 §FR-017), `alembic upgrade head` runs at orchestrator startup and migrates the restored DB forward. Risks:

- A migration may rewrite or drop a column that older rows depend on. The forward-only contract means there is no `downgrade()` to undo.
- The auto-migration is logged but not gated; the orchestrator boots with the migrated schema before any operator can review.

Mitigations:

- Extend the §2.2 quarterly drill to also restore an old (non-latest) backup, not just the most recent — verifies the migration chain is sound.
- Schema-mirror CI gate ensures the tested DDL matches migrations; a destructive change is caught pre-merge.
- For high-stakes restores: restore to a side environment, run `alembic upgrade head --sql` to inspect the pending migrations, then promote the restored environment to production after manual review.

---

## 3. Encryption-key rotation

When the operator must change `SACP_ENCRYPTION_KEY` (for example, suspected key compromise or scheduled rotation):

### 3.1 Ceremony

1. Hold loop dispatch — pause every active session via facilitator API or DB UPDATE. Confirm `loop_status running=false` events broadcast.
2. Generate a new Fernet key:
   ```python
   from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())
   ```
3. Re-encrypt every `api_key_encrypted` column under the new key. A helper script for this rotation lives outside the repo by default — operators write per-deployment.
4. Update `SACP_ENCRYPTION_KEY` in deployment config to the new key.
5. Restart orchestrator. Validate via `--validate-config-only`.
6. Resume sessions. Confirm a turn dispatches successfully (signals that `api_key_encrypted` decrypts cleanly).

### 3.2 Rollback

If rotation fails between steps 3 and 4, the old key still decrypts all rows; the deployment can resume on the old key while the operator investigates. Always retain the previous key for at least the backup-retention period.

---

## 4. Incident response

### 4.1 High false-positive `security_events` spike

**Signal**: `security_events` row insert rate jumps 5×+ over rolling 24h baseline, with `blocked=false` rows dominating.

**Triage**:
1. `SELECT layer, COUNT(*) FROM security_events WHERE timestamp > NOW() - INTERVAL '1 hour' GROUP BY layer;`
2. Identify which layer is firing — most often output_validator or exfiltration after a pattern-list update.
3. Check `routing_log.dispatch_ms` and `security_events.layer_duration_ms` for unusual durations indicating a regex pathology (ReDoS guard).
4. If false positives are operator-confirmed: revert the offending pattern via the documented update workflow.

### 4.2 Sustained `pipeline_error` events

**Signal**: rows in `security_events` with `layer='pipeline_error'` appearing repeatedly.

**Triage**:
1. Cross-ref orchestrator logs for the matching exception traceback.
2. The pipeline fails closed, so user-facing impact is "turn skipped" rather than "data leaked." Continued service is safe in degraded form.
3. Open a bug-fix branch once root cause is identified.

### 4.3 Canary leakage

**Signal**: `security_events` row with `layer='exfiltration'` and `findings` containing a canary id.

**Triage**: this is high severity — likely indicates a successful exfiltration attempt or a leak in upstream redaction. Treat as breach-investigation candidate. See GDPR Art. 33 / 34 timing considerations.

### 4.4 Breach notification timing

Operator's policy responsibility. Reference points: GDPR Art. 33 (72 hours to authority); Art. 34 (without undue delay to subject). SACP surfaces the raw signal; the operator's incident-management process owns the clock.

---

## 5. Tunable env vars

Selected operator decision points (the full catalog ships separately):

| Variable | When to raise | When to lower |
|---|---|---|
| `SACP_CONTEXT_MAX_TURNS` | Long deliberations need more history; raise toward provider context window ceiling | Token-cost pressure; lower toward MVC floor (3) |
| `SACP_CONVERGENCE_THRESHOLD` | Convergence prompts firing too often | Sessions drifting into echo-chamber without prompts firing |
| `SACP_RATE_LIMIT_PER_MIN` | Trusted internal deployment; raise to operator-monitored ceiling | Rate-limit 429s appearing on legitimate traffic |
| `SACP_REVIEW_GATE_TIMEOUT_DEFAULT` | Facilitators can't keep up; raise to give them more time | Stale held drafts piling up |
| `SACP_TURN_TIMEOUT_DEFAULT` | Slow / heavy-context providers timing out | Quick / cheap providers blocking the queue |
| `SACP_BREAKER_THRESHOLD` | Tolerant of transient flakes; raise from 3 toward 5–7 | Aggressive auto-pause on flaky providers; lower toward 2 |
| `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS` | Sessions tolerating long-running degraded turns | Aggressive cap; protects against cascading hangs |
| `SACP_ADVISORY_LOCK_WAIT_ALERT_MS` | Loud single-instance deployments raising the alert noise floor | Strict alert on cross-session lock pressure |

---

## 6. Provider degradation playbook

### 6.1 Per-provider partial outage

When a single provider (e.g., `anthropic`) is unreachable:

1. Circuit breaker per-participant opens after 5 consecutive failures. Affected participants flip to `paused-breaker`.
2. Other participants on other providers continue normally.
3. Once the upstream recovers, manual reset via facilitator API: `UPDATE participants SET consecutive_timeouts = 0 WHERE provider = 'anthropic'` (or the dedicated reset tool, when implemented).

### 6.2 Retry-storm prevention

The orchestrator uses bounded per-call retries; the breaker provides the second-line protection. There is no global retry-storm-detector — operator must watch `routing_log.dispatch_ms` percentiles for sudden growth.

### 6.3 Multi-provider failover (Phase 3)

Phase 1 does NOT support automatic provider failover for a single participant. Each participant has ONE configured provider; if that provider fails, the participant's circuit breaker trips. Manual recovery: operator updates `participants.provider` + `participants.api_key_encrypted` to a new provider, then resets the breaker. Phase 3 trigger documented in spec 003 Reliability section.

### 6.4 Compound-retry alert escalation (003 §FR-031)

Two operator-monitorable signals from compound-retry instrumentation:

| Signal | `routing_log.reason` | Severity | Action |
|---|---|---|---|
| compound_retry_warn | `compound_retry_warn` (turn elapsed > 2× per-attempt timeout, default 360 s) | Informational | Monitor trend; investigate if rate climbs |
| compound_retry_exhausted | `compound_retry_exhausted` (turn skipped at hard cap, default 600 s) | Actionable | Investigate participant's provider health; consider raising `SACP_BREAKER_THRESHOLD` if transient |

Recommended alert: `compound_retry_exhausted` rate > 1 per session per hour over a rolling 24-hour window.

### 6.5 Advisory-lock contention alert (003 §FR-032)

`routing_log.advisory_lock_wait_ms` captures lock-acquisition latency per turn. Single-instance Phase 1 deployments should normally see sub-10 ms values.

Operator alert: rolling-window mean > `SACP_ADVISORY_LOCK_WAIT_ALERT_MS` (default 100 ms) over 5 minutes indicates cross-session lock pressure. Common causes:

1. Long-running transactions on the same `branch_id` (cross-ref 003 §FR-022 lock scope)
2. Multi-instance deployment without single-loop-per-session coordination (Phase 1 single-instance assumption violated)
3. DB primary failover mid-acquisition (lock state lost; next attempt re-acquires)

---

## 7. Pattern-list update workflow

Short version: incident → single-PR pull (corpus + regression test + pattern + runbook update) → zero-regression check → land within one cycle. The operator's role is to capture incidents as they appear in `security_events` and route them into this workflow.

### 7.1 Roles

- **Pattern reviewer** — maintains `src/security/*.py` modules; reviews each PR for pattern correctness + regression-test coverage
- **Red-team runbook maintainer** — appends incident entries to `docs/red-team-runbook.md` (local-only) when patterns ship
- **Cadence** — incident-driven (no scheduled review); 007 §FR-017 mandates within-one-cycle landing after a confirmed incident

### 7.2 Regression-test requirement

Every pattern-list PR MUST:

1. Add a regression test against `tests/fixtures/adversarial_corpus.txt` for the new pattern
2. Verify zero new false positives against `tests/fixtures/benign_corpus.txt`
3. Re-run the existing corpus-regression test suite (no-regression invariant)

Canonical workflow: `docs/pattern-list-update-workflow.md` (012 US8 deliverable). The corpora are the canonical regression-test surface.

### 7.3 False-positive feedback loop

Operator observes elevated `security_events.blocked=false` rate per layer (§4.1 alert) → opens a tracking issue → routes the offending pattern through this workflow. The regression-test requirement ensures the revision doesn't regress existing patterns.

---

## 8. Audit follow-through process

The audit follow-through tracker (gitignored, local-only) is the operator-visible status board for cross-cutting items from the pre-Phase-3 audit sweep. Status flips as PRs land. Discovery of new cross-cutting work adds rows; closing rows requires a PR reference.

The board is local-only by policy, not committed to the repo. Operators running multiple deployments maintain their own copy.

---

## 9. Incident catalog

The internal red-team runbook is the cumulative list of red-team incidents and their resolution. New entries land per the pattern-list update workflow. Operator should review the catalog after every upstream-provider model change and after every detector pattern update to confirm the historic incidents still close cleanly against the corrected pipeline.

---

## 10. Database operations

### 10.1 Connection pool tuning

asyncpg pool defaults: `min_size=1, max_size=10`. Tunable via `SACP_DB_POOL_MIN_SIZE` / `SACP_DB_POOL_MAX_SIZE` (reserved env vars; default unset).

Sizing guidance:

- Single-instance deployment, ≤ 10 active sessions: defaults are fine
- Single-instance, 10–50 active sessions: raise `max_size` to ~30
- Multi-instance (Phase 3): each instance reserves `max_size` connections; total reserved = `instance_count × max_size`, must stay under Postgres' `max_connections`

Symptoms of pool starvation:

- `routing_log.persist_ms` jumps to 100 ms+ when historical baseline is sub-10 ms
- asyncpg `PoolTimeoutError` / `TooManyConnectionsError` exceptions in logs

### 10.2 DB failover behavior

Mid-transaction failover (DB drops between INSERT statements during a turn):

- asyncpg raises `ConnectionDoesNotExistError` or `InterfaceError`
- The turn coroutine catches the exception per 003 §FR-021 (loop never halts), logs `routing_log.reason='dispatch_error'`, advances to next participant
- The failed participant's circuit breaker increments per 003 §FR-015; auto-pause after 3 consecutive failures
- Partially-written rows are rolled back via the surrounding transaction (`async with conn.transaction()`); no orphans

Symptoms of sustained DB connectivity issues:

- All sessions show `routing_log.reason='dispatch_error'` over a rolling 5-minute window
- `/healthz` returns 503 (when the endpoint lands per 006 reliability)
- `pg_stat_activity` shows zero connections from the orchestrator instance

Recovery: orchestrator restart picks up a fresh pool against the recovered DB; in-flight turns are abandoned (RPO=0 for committed turns; cross-ref §10.4).

### 10.3 Standby / replica strategy

Phase 1 contract: **single logical Postgres, single writer**. The orchestrator's advisory-lock semantics (003 §FR-022) require the writer to be the same instance handling the turn-loop coroutine.

Read-replica strategy for read-only operations:

- Phase 1: not supported — all reads go through the primary
- Phase 3 trigger: any deployment where read load justifies replica offload. Implementation surface: a separate `SACP_DATABASE_READ_URL` env var routing read-only queries (010 debug-export, GET endpoints) to the replica; writes always to primary. The advisory-lock writer remains the primary.

DB HA stack (Patroni / Crunchy / managed cloud service): SACP does not orchestrate failover — the operator's HA stack is responsible. The orchestrator's connection pool reconnects on its next request after the new primary accepts connections.

### 10.4 RTO / RPO

- **RPO** (recovery point objective): zero for committed turns. Every turn that returns success has its `messages` row, `routing_log` row, and `usage_log` row durable. In-flight turns interrupted by orchestrator crash are abandoned (no partial state — transactional rollback).
- **RTO** (recovery time objective): orchestrator restart-to-first-turn ~5–10 seconds. Boot sequence: env-var validation (~1 s) + DB pool init (~1 s) + alembic check (1–3 s) + port bind (instant). First turn dispatches when a session connects and the loop coroutine wakes.
- Database failover RTO depends on the operator's Postgres HA stack; SACP does not orchestrate DB failover.

---

## 11. Turn-loop operations

### 11.1 Loop lifecycle (003 §FR-021, §FR-027)

- **SIGTERM** → uvicorn graceful-shutdown cancels the loop coroutine; in-flight turns abandoned (transactional rollback, no partial state)
- **Startup** → no per-turn resumption; persisted state is the source of truth; sessions with `status='active'` resume on next eligible participant
- **Single-loop-per-session (FR-027)** → enforced implicitly via single-deployment topology; multi-instance deployments must wait for Phase 3 session-lease coordination

RTO ~5–10 s for orchestrator restart-to-first-turn (boot sequence in §1.4).

### 11.2 Operator override for stuck loops

Phase 1:

1. Pause via facilitator API or `UPDATE sessions SET status='paused' WHERE id=...`
2. Process restart (RTO ~5–10 s; abandons in-flight turns across ALL sessions)

Phase 3 trigger: any deployment where individual sessions can wedge without affecting others. Implementation: `/tools/admin/kill_loop?session_id=...` admin endpoint.

### 11.3 Interrupt-queue saturation

Phase 1 has no enforced cap on `interrupt_queue` per session; pathological accumulation (1000+ pending) grows per-turn latency O(n).

Operator-side observability: `SELECT session_id, COUNT(*) FROM interrupt_queue WHERE delivered_at IS NULL GROUP BY session_id HAVING COUNT(*) > 100;` flags sessions worth investigating.

Phase 3 trigger: any deployment observing pathological accumulation; implementation: `MAX_PENDING_INTERRUPTS_PER_SESSION` cap + oldest-dropped behavior.

### 11.4 Budget-window edges (003 §FR-028)

Budget enforcement uses rolling trailing windows (`NOW() - INTERVAL '1 hour'` / `NOW() - INTERVAL '1 day'`), NOT calendar-aligned. Midnight has no semantic effect on budget rollover. A turn at 23:59:59 charges against the rolling 24-hour window starting at 23:59:59 yesterday.

Operator implication: budget-utilization dashboards SHOULD use the same rolling window, not calendar-day SUM, to match enforcement semantics.

### 11.5 Cadence-preset runtime switching

Cadence preset (`SACP_CADENCE_PRESET`) read at startup; per-session override via cadence config UI takes effect on next turn (snapshot semantics per 003 §FR-025). Switching from `sprint` to `cruise` mid-session is supported. Facilitator role gate applies at the API layer (002 §FR-010).

---

## 12. Security pipeline operations

### 12.1 Alert thresholds (007 ops)

| Alert | Source | Threshold | Action |
|---|---|---|---|
| FP rate spike per layer | `security_events WHERE blocked=false` insert rate | 5× rolling 24h baseline | Triage §4.1 |
| Layer-error spike | `security_events WHERE layer='pipeline_error'` insert rate | ≥3 per session per hour | Triage §4.2 |
| Canary leakage | `security_events WHERE layer='output_validator' AND findings ~ 'canary'` | Any | Triage §4.3 (high severity) |
| pipeline_total_ms P95 | `routing_log.pipeline_total_ms` rolling P95 | > 100 ms over 5 minutes | Investigate per-layer breakdown via `security_events.layer_duration_ms` |

### 12.2 security_events query patterns

Common operator queries:

```sql
-- High-FP layer in the last hour
SELECT layer, COUNT(*) FROM security_events
WHERE timestamp > NOW() - INTERVAL '1 hour' AND blocked=false
GROUP BY layer ORDER BY COUNT(*) DESC;

-- Per-session blocked-response rate (last 24h)
SELECT session_id, COUNT(*) FROM security_events
WHERE timestamp > NOW() - INTERVAL '24 hours' AND blocked=true
GROUP BY session_id ORDER BY COUNT(*) DESC LIMIT 20;

-- Canary-leakage candidates (high severity)
SELECT session_id, speaker_id, turn_number, findings
FROM security_events
WHERE layer='output_validator' AND findings::text LIKE '%canary%'
ORDER BY timestamp DESC;
```

Facilitator UI access: per-session findings surface via the review-gate UI (007 §FR-016). Operator post-incident: query `security_events` directly. Automated alerting: operator's choice of Grafana / Sentry / syslog.

### 12.3 Pipeline-bypass invariants (007 SC-007)

Production AI dispatch always flows through `_validate_and_persist`. Operator-side checks:

- Any new `/tools/*` endpoint that triggers an LLM call: verify it routes through `_validate_and_persist` before persisting any AI output
- Code review check: `grep -r "litellm.acompletion" src/` should show zero call sites outside the orchestrator's dispatch path

### 12.4 LLM-as-judge feature flag (Phase 3 trigger)

Activation surface (when wired):

- `SACP_LLM_JUDGE_ENABLED` (boolean) — gates the layer
- `SACP_LLM_JUDGE_MODEL` — judge model identifier
- `SACP_LLM_JUDGE_TIMEOUT_MS` — per-call timeout (default 1500 ms)

Triggers documented in spec 007 Operations section.

---

## 13. Web UI operations

### 13.1 Deploy semantics

- **Single-instance** (Phase 1): all WS connections terminate at one orchestrator process. On redeploy, WS connections close; clients reconnect via 011 §FR-014 (exponential backoff).
- **Multi-instance** (Phase 3): requires WS session affinity OR externalized `SessionStore`. Trigger: HA Web UI requirements.
- **Single-tenant only**: one operator, one DB, one origin per deployment.

### 13.2 Reverse-proxy configurations

Phase 1 documented configurations: Caddy, nginx, Cloudflare.

**Required by all**:

- WS upgrade headers preserved (`Upgrade: websocket`, `Connection: Upgrade`)
- `X-Forwarded-For` set (consumed by 002 §FR-023 when `SACP_TRUST_PROXY=1`)
- `X-Forwarded-Proto: https` set so the orchestrator emits HTTPS-only redirects
- `/csp-report` POSTs allowed through
- `X-SACP-Request: 1` (custom CSRF header per 011 SR-006) NOT stripped on mutations
- WS frame size cap (256 KB per 011 SR-001a) preserved or set higher

**Caddy sample**:

```caddyfile
example.com {
    reverse_proxy /api/* localhost:8750
    reverse_proxy /ws/* localhost:8751 {
        header_up Upgrade {http.request.header.Upgrade}
        header_up Connection {http.request.header.Connection}
    }
    reverse_proxy localhost:8751
}
```

**nginx sample**:

```nginx
location /ws/ {
    proxy_pass http://localhost:8751;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}
```

**Cloudflare**: enable WebSockets in Network settings; set `X-Forwarded-Proto` via Transform Rules; ensure WAF rules don't strip `X-SACP-Request` header.

### 13.3 HTTP vs HTTPS posture sanity check

Pre-deploy verification (operator-side):

```bash
# Production deploy: HTTPS expected, INSECURE_COOKIES must be unset/0
echo "$SACP_WEB_UI_INSECURE_COOKIES" | grep -E '^(0|)$' || echo "WARN: insecure cookies enabled in production"

# Verify HTTPS reachability
curl -sI https://your-deploy.example.com/ | head -1 | grep -q "200\|3"
```

Misconfiguration to avoid: HTTPS deploy with `SACP_WEB_UI_INSECURE_COOKIES=1` silently downgrades cookie security.

### 13.4 CDN dependency

CDN origins (`cdn.jsdelivr.net`, `unpkg.com`) availability is a deployment dependency. If unavailable, the Web UI fails to load. Phase 1 has no fallback bundle.

Operator monitoring:

- Browser-side: CDN errors surface as `/csp-report` violations (when CSP blocks them) or browser console errors (when CDN responds with non-200)
- Server-side: not visible to the orchestrator; CDN failures happen browser-side

Phase 3 mitigation: server-side bundling (eliminates CDN dependency). Trigger documented in spec 011 Compliance / Privacy + Operations sections.

### 13.5 CSP report log volume

`/csp-report` endpoint logs at WARNING level. Misconfigured CSP can flood logs (e.g., a CDN URL not in `connect-src` triggers a report on every page load).

Operator mitigation:

- Monitor CSP-report ingest rate via the WARNING log stream
- If sustained > 10/sec for the same blocked-URL: fix the CSP rather than let logs grow
- Sanity check after deploy: load the UI, watch logs for unexpected CSP violations

Phase 3 trigger: any deployment observing log-volume DoS via CSP reports; implementation: per-origin rate-limit on `/csp-report`.

### 13.6 Browser cache invalidation

- SR-008 `Cache-Control: no-store` on `/` (HTML) and `/api/*` ensures fresh fetch on each load
- CDN scripts versioned in URL (`react@18.2.0`); cache invalidation = URL change on version bump
- Service workers / PWA: NOT used in Phase 1; no aggressive cache pinning

---

## 14. Cross-references

- `docs/retention.md` — per-table retention policy; pairs with §2.5
- `docs/env-vars.md` — canonical env-var catalog; pairs with §1, §5, §10, §11
- `docs/compliance-mapping.md` — GDPR / NIST mapping; pairs with §4 incident response
- `docs/pattern-list-update-workflow.md` — canonical pattern-update flow; pairs with §7
- `docs/red-team-runbook.md` (local-only) — incident catalog feeding pattern updates; pairs with §9
- 001 Operations section — architectural deferrals + Phase 3 triggers (sister)
- 003 Operations + Reliability sections — turn-loop ops contracts (sister to §6, §11)
- 003 §FR-022, §FR-027 — advisory lock + single-writer contract
- 007 Operations section — security-pipeline ops contracts (sister to §4, §7, §12)
- 007 §FR-013 — fail-closed pipeline invariant
- 007 §FR-017 — pattern-list maintenance contract
- 011 Operations section — Web UI ops contracts (sister to §13)
- 011 SR-001, SR-001a, SR-002, SR-006 — CSP, WS frame cap, security headers, CSRF
