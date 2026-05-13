# Implementation Plan: Prometheus-Format Metrics

**Branch**: `016-prometheus-metrics` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/016-prometheus-metrics/spec.md`

## Summary

Mount a Prometheus-format `/metrics` endpoint on the SACP orchestrator (port 8750) gated by `SACP_METRICS_ENABLED`. Replace the pre-016 in-memory counter stub in `src/observability/metrics.py` with real `prometheus_client` objects while preserving all spec 019 and 015 call sites unchanged. Six metric families: participant tokens/cost, provider health, convergence quality, routing decisions, rate-limit rejections. Session-scoped cardinality with grace-window eviction on session end.

## Technical Context

**Language/Version**: Python 3.14.4 (Constitution §6.8 slim-bookworm)
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest (existing); `prometheus-client==0.25.0` (new, pinned per Constitution §6.3)
**Storage**: N/A — all metrics live in the `prometheus_client` CollectorRegistry (in-memory); no DB writes; no alembic migration
**Testing**: pytest (existing)
**Target Platform**: Linux server (Docker / slim-bookworm)
**Project Type**: Single project
**Performance Goals**: /metrics P95 <= 500ms at 100 sessions x 5 participants; per-turn metric overhead within V14 budget
**Constraints**: No DB reads on /metrics hot path; O(active_series) response time; additive when SACP_METRICS_ENABLED=false

**Scale/Scope**: Bounded by active_sessions x max_participants_per_session; terminated sessions evicted within SACP_METRICS_SESSION_GRACE_S

## Constitution Check

- **V1 (Sovereignty)**: No cross-participant label leakage. `participant_id_hash` uses first 8 hex chars of SHA-256(participant_id) — privacy-safe, non-reversible within the metric label surface.
- **V4 (Facilitator Powers)**: `/metrics` is operator-tier (no participant auth required); gated by `SACP_METRICS_ENABLED` which is an operator-side env var.
- **V7 (25/5 limits)**: No new participant-visible surface. Metric label cardinality is bounded by FR-005.
- **V16 (3 env vars validated before tasks)**: `SACP_METRICS_ENABLED`, `SACP_METRICS_SESSION_GRACE_S`, `SACP_METRICS_BIND_PATH` — all three validators land in `src/config/validators.py` + `docs/env-vars.md` before `/speckit.tasks`.

## Project Structure

### Documentation (this feature)

```text
specs/016-prometheus-metrics/
├── plan.md              # This file
├── research.md          # prometheus_client rationale, cardinality, eviction, migration
├── data-model.md        # In-memory metric families; no DB tables
├── quickstart.md        # Operator enablement steps
├── contracts/
│   └── metrics-endpoint.md   # GET /metrics contract
└── tasks.md             # Phase 2-5 + Polish tasks
```

### Source Code (repository root)

```text
src/
├── observability/
│   └── metrics.py          # REPLACED: real prometheus_client objects; same external API
│   └── metrics_registry.py # NEW: REGISTRY + session-eviction helpers
├── mcp_server/
│   └── metrics_router.py   # NEW: GET /metrics FastAPI router
│   └── app.py              # PATCHED: conditionally include metrics_router
├── config/
│   └── validators.py       # PATCHED: 3 new validators + VALIDATORS tuple entries

docs/
├── env-vars.md             # PATCHED: 3 new SACP_METRICS_* sections
└── metrics.md              # NEW: 6 metric families reference

tests/
├── test_016_metrics_endpoint.py   # NEW
├── test_016_metrics_counters.py   # NEW
└── test_016_session_eviction.py   # NEW
```

**Structure Decision**: Single project. Metric registry split to `metrics_registry.py` to keep `metrics.py` focused on the public API surface that spec 019 and 015 call sites import. The router lives in `src/mcp_server/` alongside existing routers.

## Complexity Tracking

No Constitution violations.
