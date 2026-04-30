# Operations Requirements Quality Checklist: MCP Server

**Purpose**: Validate the quality, clarity, and completeness of operational requirements in the MCP Server spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 8 items pass cleanly, 22 have findings. The MCP server is the primary deployable surface — startup behavior, env-var contract, observability, deploy/rollback, and incident response all have operator implications. The spec covers some env vars (SACP_CORS_ORIGINS, SACP_ENABLE_DOCS) but lacks systematic operations posture.

## Configuration Surface

- [x] CHK001 Is the complete env-var allowlist enumerated with type, default, and effect?
  [PARTIAL]. Spec mentions `SACP_CORS_ORIGINS`, `SACP_ENABLE_DOCS`, port 8750. Other vars (`SACP_AUDIT_RETENTION_DAYS`, `SACP_ENCRYPTION_KEY`, `SACP_DB_URL`, etc.) are scattered across other specs. Single canonical list would help operators. Cross-ref 010 §FR-7 maintains a `_CONFIG_KEYS` allowlist for debug-export but that's snapshot-side, not operations-side.

- [x] CHK002 Are required vs. optional env vars distinguished, with fail-closed startup if required vars are missing?
  [GAP]. `SACP_ENCRYPTION_KEY` is required (per 001 Edge Cases: "fail closed if encryption key unavailable") but spec doesn't enumerate other required vars or codify the fail-closed pattern uniformly.

- [x] CHK003 Are env-var precedence rules specified (env var vs. config file vs. CLI flag)?
  [GAP]. Single source (env var). Worth declaring explicitly so operators don't expect a config file.

- [x] CHK004 Are sensitive env vars (API keys, encryption keys, DB URLs) documented as never-logged and never-included-in-snapshots?
  [PARTIAL]. 010 §FR-7 covers debug-export; 007 §FR-012 covers log scrubbing. Cross-ref to operations is implicit.

- [x] CHK005 Is the CORS regex (FR-016 octet validation) testable as a unit/regression test?
  [PARTIAL]. The regex is in code; spec describes the fix but doesn't mandate a test corpus (192.168.999.999 negative, 192.168.1.1 positive, etc.).

## Startup & Healthcheck

- [x] CHK006 Is a `/healthz` or equivalent liveness endpoint specified?
  [GAP]. SC-005 says "server starts and accepts connections on the configured port" but no spec'd healthcheck endpoint. Container orchestrators (K8s, docker-compose healthcheck) need one.

- [x] CHK007 Is a readiness check specified (DB reachable, encryption key valid, alembic migrations up-to-date)?
  [GAP]. Liveness ≠ readiness. Spec doesn't separate.

- [x] CHK008 Are startup-time bounds specified (the server should be ready within N seconds)?
  [GAP]. Cold start includes alembic upgrade + FastAPI app construction; can be slow on first deploy.

- [x] CHK009 Is graceful shutdown specified (drain in-flight SSE connections, finish pending DB writes)?
  [GAP]. uvicorn handles SIGTERM by default but spec doesn't pin grace period or drain semantics. Cross-ref 005 CHK030 (in-flight summarization shutdown).

- [x] CHK010 Is alembic-migration behavior on startup specified (auto-run vs. operator-triggered)?
  [PARTIAL]. Dockerfile CMD: `alembic upgrade head && python -m src.run_apps`. Auto-run is the default. Spec doesn't pin this — operators may want migrations decoupled from app startup for safety.

## Deployment

- [x] CHK011 Are deployment topologies specified (single-instance vs. multi-instance)?
  [GAP]. SACP is implicitly single-instance (the orchestrator's per-session lock is in-memory). Multi-instance deploy would silently break session ordering. Worth explicitly declaring.

- [x] CHK012 Are zero-downtime deploy semantics specified (blue/green, rolling)?
  [GAP]. With single-instance + in-memory locks, zero-downtime requires session-affinity routing or shutdown coordination — neither is specified.

- [x] CHK013 Are rollback semantics specified (alembic downgrades, forward-only migrations)?
  [DRIFT]. 001 §FR-017: "schema evolution through versioned, forward-only migrations." So no downgrade. Rollback requires DB restore from snapshot. Operations spec is silent on this constraint.

- [x] CHK014 Is the Docker image tagging contract specified (sha-<commit>, latest, production)?
  [PARTIAL]. `.github/workflows/build-image.yml` produces `latest` and `sha-<commit>`. Spec doesn't surface this as the consumer contract.

- [x] CHK015 Are the deployment-time resource requirements specified (CPU, memory, disk for embedding cache)?
  [GAP]. Memory floor (≈700MB image post CPU-only-torch fix; ~250MB runtime base + ~90MB embedding model in-process) is unspecified.

## Observability

- [x] CHK016 Are structured-log requirements specified (JSON format, log levels, correlation IDs, request IDs)?
  [PARTIAL]. CHK033 closed as accepted residual: "basic FastAPI logging covers it." Worth elevating: a session-correlation ID would make multi-turn debugging much easier.

- [x] CHK017 Are metrics requirements specified (per-endpoint latency, error rate, SSE-connection count)?
  [GAP]. No /metrics endpoint, no Prometheus / OTLP integration mentioned.

- [x] CHK018 Are tracing requirements specified (OpenTelemetry, distributed traces across MCP → orchestrator → DB)?
  [GAP].

- [x] CHK019 Is alerting specified (which conditions page on-call, which file a ticket)?
  [GAP]. With no metrics, no alerts. Operations spec should at minimum name the conditions worth alerting on (DB down, encryption key missing, sustained 5xx rate).

- [x] CHK020 Is the security_events table (007 §FR-015) cross-referenced as a feed for security-monitoring tooling?
  [GAP]. Could be — would need an explicit operations-mapping note.

## Capacity & Limits

- [x] CHK021 Are SSE-connection limits specified per-process / per-participant?
  [PARTIAL]. FR-017 explicitly defers per-participant SSE caps to Phase 3 with a trigger. Per-process cap is unspecified.

- [x] CHK022 Are concurrent-session limits specified?
  [GAP]. Implicit bound is "however many fit in memory."

- [x] CHK023 Are rate-limit (009-rate-limiting) operational tunables documented in this spec?
  [GAP]. 009 §spec covers them; 006 spec doesn't surface them as operations knobs.

- [x] CHK024 Is the disk-growth profile bounded (messages, logs, embeddings, summaries)?
  [GAP]. Cross-ref 001 CHK021-023 (no retention policy on most tables).

## Backup & Recovery

- [x] CHK025 Are backup requirements specified (frequency, retention, restore SLO)?
  [GAP]. Operator concern but operations spec should at minimum reference what data MUST be backed up.

- [x] CHK026 Are restore-validation requirements specified (test restore monthly, document procedure)?
  [GAP].

- [x] CHK027 Is the restore-from-backup → app-startup sequence specified for new operators?
  [GAP]. With auto-migrate on startup (CHK010), restoring an OLDER backup against a NEWER image would auto-upgrade — usually fine, but if `forward-only` (FR-017) hits a bug-introducing migration, recovery is harder.

## Incident Response

- [x] CHK028 Is on-call escalation specified (who is paged, when, with what runbook)?
  [GAP].

- [x] CHK029 Is post-incident review specified (security_events table feeds RCA; admin_audit_log captures actions)?
  [GAP].

## Operator Self-Service

- [x] CHK030 Is the FR-015 "production leaves SACP_ENABLE_DOCS unset" guidance paired with an operator-side smoke test that the production deploy actually has docs disabled?
  [GAP]. No deploy-time check. A misconfigured prod could ship with docs enabled and the spec wouldn't catch it.

## Notes

- 30 items audited. The MCP server has reasonable security-side hardening (FR-013 SSE bound, FR-014 traceback scrub, FR-015 docs gate, FR-016 CORS regex) but operations posture is implicit.
- Highest-leverage findings to convert into spec amendments:
  - CHK006 / CHK007 (specify `/healthz` + `/readyz` endpoints — single biggest operator-experience improvement, unblocks Kubernetes / docker-compose healthchecks).
  - CHK011 (declare single-instance deployment as the intended topology — closes a footgun for operators trying to scale horizontally).
  - CHK010 (pin alembic auto-migrate vs. operator-triggered as an explicit choice — currently de-facto auto, which is risky for major migrations).
  - CHK001 (consolidate env-var contract into one location — currently scattered across 11 specs).
  - CHK009 (graceful shutdown semantics — pairs with 005 CHK030).
- Lower-priority but useful:
  - CHK016 / CHK017 / CHK018 (observability stack — Phase 3 work, but worth declaring intent).
  - CHK013 (rollback constraints from 001 §FR-017 surfaced here for operator awareness).
  - CHK030 (deploy-time smoke test for FR-015 docs gating).
- Sister checklists `requirements.md` and `security.md` (closed 2026-04-29). Operations is the natural Tier 3 axis for the deployable surface. Cross-ref 010 §FR-7 (config snapshot allowlist) and 003 turn-loop for the in-process work.
