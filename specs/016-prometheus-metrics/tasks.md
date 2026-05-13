# Tasks: Prometheus-Format Metrics (spec 016)

**Branch**: `016-prometheus-metrics` | **Date**: 2026-05-13

## Phase 2 Foundational — V16 validators + docs gate

### US0-T001: 3 env-var validators

Add `validate_metrics_enabled`, `validate_metrics_session_grace_s`, `validate_metrics_bind_path` to `src/config/validators.py` and register all three in `VALIDATORS` tuple.

- `SACP_METRICS_ENABLED`: bool (`true`/`false` case-insensitive or `1`/`0`), default false
- `SACP_METRICS_SESSION_GRACE_S`: int in [5, 300], default 30
- `SACP_METRICS_BIND_PATH`: string starting with `/`, alphanumeric+dashes after slash, default `/metrics`

**Status**: [DONE]

### US0-T002: docs/env-vars.md — 3 SACP_METRICS_* sections

Add the three new vars to `docs/env-vars.md` with all six standard fields.

**Status**: [DONE]

### US0-T003: prometheus-client dependency

Add `prometheus-client==0.25.0` to `pyproject.toml` `[project.dependencies]`.

**Status**: [DONE]

### US0-T004: docs/metrics.md

Create `docs/metrics.md` enumerating all 6 metric families: name, type, description, labels, bounded enumerations, cardinality bound, source spec section (FR-013).

**Status**: [DONE]

## Phase 3 — US1: Operator sees participant spend

### US1-T005: metrics_registry.py

Create `src/observability/metrics_registry.py` with:
- `REGISTRY` (CollectorRegistry)
- All 6 real prometheus_client Counter/Gauge objects on REGISTRY
- `MetricsEvictionTracker` class
- `schedule_session_eviction(session_id, grace_s)` function
- `evict_session(session_id)` function

**Status**: [DONE]

### US1-T006: metrics.py rewrite

Replace `_CounterFamily`/`_BoundCounter` internals in `src/observability/metrics.py` with wrappers around real prometheus_client objects from metrics_registry. Preserve the full external API: `sacp_rate_limit_rejection_total.labels(**kw).inc()`, `.get_sample_value()`, `.samples()`, `reset_for_tests()`, `increment_network_rate_limit_rejection()`, `get_circuit_breaker_metrics()`.

**Status**: [DONE]

### US1-T007: metrics_router.py

Create `src/mcp_server/metrics_router.py` with `GET /metrics` route gated by `SACP_METRICS_ENABLED`. Returns `generate_latest(REGISTRY)` with `CONTENT_TYPE_LATEST`.

**Status**: [DONE]

### US1-T008: app.py integration

Add conditional `app.include_router(metrics_router)` to `_include_routers()` in `src/mcp_server/app.py` following the pattern of spec 029's audit viewer.

**Status**: [DONE]

### US1-T009: loop.py token/cost wiring

In `_log_usage()` in `src/orchestrator/loop.py`, wire `sacp_participant_tokens_total` and `sacp_participant_cost_usd_total` increments after the existing `log_repo.log_usage()` call.

**Status**: [DONE]

## Phase 4 — US2: Provider health visible

### US2-T010: provider counter wiring

In `_assemble_and_dispatch()` (success branch) and `_record_failure_and_announce()` (failure branch) in loop.py, wire `sacp_provider_request_total` increments with `{provider_kind, outcome}` labels.

**Status**: [DONE]

## Phase 5 — US3: Session quality + routing visible

### US3-T011: convergence gauge wiring

In `_compute_turn_delay()` in loop.py, wire `sacp_session_convergence_similarity` gauge update after `self._convergence.process_turn()` returns a similarity score.

**Status**: [DONE]

### US3-T012: routing counter wiring

In `_log_routing()` and `_log_skip_entry()` in loop.py, wire `sacp_routing_decision_total` counter increments.

**Status**: [DONE]

### US3-T013: session eviction hook

In `src/mcp_server/app.py` session-teardown path (or wherever sessions are archived/ended), call `schedule_session_eviction(session_id)`. Locate the session-end signal (status update to `paused`/`archived`).

**Status**: [DONE]

## Polish

### P-T014: SC-002 performance note

The `/metrics` endpoint uses `generate_latest()` which is O(active_series) in-memory with no DB reads. Per-turn metric updates are O(1) counter increments. No additional profiling needed for v1; SC-002 is satisfied by design.

**Status**: [DONE]

### P-T015: V18 traceability audit

Verify FR-001 through FR-015 and SC-001 through SC-008 are all addressed by the implementation.

**Status**: [DONE]

### P-T016: Seven closeout preflights

Run all 7 speckit preflights before marking Implemented.

**Status**: [DONE]
