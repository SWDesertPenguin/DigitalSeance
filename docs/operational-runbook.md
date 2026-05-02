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

---

## 6. Provider degradation playbook

### 6.1 Per-provider partial outage

When a single provider (e.g., `anthropic`) is unreachable:

1. Circuit breaker per-participant opens after 5 consecutive failures. Affected participants flip to `paused-breaker`.
2. Other participants on other providers continue normally.
3. Once the upstream recovers, manual reset via facilitator API: `UPDATE participants SET consecutive_timeouts = 0 WHERE provider = 'anthropic'` (or the dedicated reset tool, when implemented).

### 6.2 Retry-storm prevention

The orchestrator uses bounded per-call retries; the breaker provides the second-line protection. There is no global retry-storm-detector — operator must watch `routing_log.dispatch_ms` percentiles for sudden growth.

---

## 7. Pattern-list update workflow

Short version: incident → single-PR pull (corpus + regression test + pattern + runbook update) → zero-regression check → land within one cycle. The operator's role is to capture incidents as they appear in `security_events` and route them into this workflow.

---

## 8. Audit follow-through process

The audit follow-through tracker (gitignored, local-only) is the operator-visible status board for cross-cutting items from the pre-Phase-3 audit sweep. Status flips as PRs land. Discovery of new cross-cutting work adds rows; closing rows requires a PR reference.

The board is local-only by policy, not committed to the repo. Operators running multiple deployments maintain their own copy.

---

## 9. Incident catalog

The internal red-team runbook is the cumulative list of red-team incidents and their resolution. New entries land per the pattern-list update workflow. Operator should review the catalog after every upstream-provider model change and after every detector pattern update to confirm the historic incidents still close cleanly against the corrected pipeline.
