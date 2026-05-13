# Data Model: Prometheus-Format Metrics (spec 016)

## Storage

No database tables. All metric state is in-memory, held by a single `prometheus_client.CollectorRegistry` instance (`REGISTRY`) in `src/observability/metrics_registry.py`. No alembic migration. No schema changes.

## Metric Families

### 1. `sacp_rate_limit_rejection_total`

| Field | Value |
|---|---|
| Type | Counter |
| Help | Rate-limit rejections by class |
| Labels | `endpoint_class`, `exempt_match` |
| Label values | `endpoint_class`: `network_per_ip`, `app_layer_per_participant`; `exempt_match`: `true`, `false` |
| Cardinality bound | 2 x 2 = 4 series maximum (non-session-scoped) |
| Source | spec 019 rejection path in `src/middleware/network_rate_limit.py` |
| Session-scoped | No |

### 2. `sacp_participant_tokens_total`

| Field | Value |
|---|---|
| Type | Counter |
| Help | Provider token usage per session participant and direction |
| Labels | `session_id`, `participant_id_hash`, `direction` |
| Label values | `direction`: `prompt`, `completion` |
| Cardinality bound | active_sessions x participants_per_session x 2 |
| Source | `response.input_tokens` / `response.output_tokens` in `_log_usage()` in `src/orchestrator/loop.py` |
| Session-scoped | Yes — evicted within SACP_METRICS_SESSION_GRACE_S after session end |

### 3. `sacp_participant_cost_usd_total`

| Field | Value |
|---|---|
| Type | Counter |
| Help | Provider cost in USD per session participant |
| Labels | `session_id`, `participant_id_hash` |
| Label values | — |
| Cardinality bound | active_sessions x participants_per_session |
| Source | `response.cost_usd` in `_log_usage()` in `src/orchestrator/loop.py` |
| Session-scoped | Yes |

### 4. `sacp_provider_request_total`

| Field | Value |
|---|---|
| Type | Counter |
| Help | Provider dispatch requests by kind and outcome |
| Labels | `provider_kind`, `outcome` |
| Label values | `provider_kind`: `litellm`, `mock`; `outcome`: `success`, `error_5xx`, `error_4xx`, `timeout`, `auth_error`, `rate_limit`, `circuit_open` |
| Cardinality bound | 2 x 7 = 14 series maximum (non-session-scoped) |
| Source | dispatch success/failure path in `_assemble_and_dispatch()` and `_route_validated_response()` in loop.py |
| Session-scoped | No |

### 5. `sacp_session_convergence_similarity`

| Field | Value |
|---|---|
| Type | Gauge |
| Help | Last convergence similarity score for a session (0.0=diverged, 1.0=converged) |
| Labels | `session_id` |
| Label values | — |
| Sentinel | Absent (not set) when session has not yet produced a similarity score |
| Cardinality bound | active_sessions |
| Source | `_compute_turn_delay()` in loop.py, via `self._convergence.process_turn()` return value |
| Session-scoped | Yes |

### 6. `sacp_routing_decision_total`

| Field | Value |
|---|---|
| Type | Counter |
| Help | Routing decisions per session and decision class |
| Labels | `session_id`, `routing_mode`, `skip_reason` |
| Label values | `routing_mode`: derived from `decision.action` field; `skip_reason`: `""` (dispatched), `circuit_open`, `budget_exceeded`, `skipped` |
| Cardinality bound | active_sessions x routing_mode_count x skip_reason_count |
| Source | `_log_routing()` and `_log_skip_entry()` in loop.py |
| Session-scoped | Yes |

## Session Eviction Mechanism

A `MetricsEvictionTracker` (in `src/observability/metrics_registry.py`) maintains a per-session set of registered label tuples for each session-scoped metric family. When a session ends, the caller invokes `schedule_session_eviction(session_id)`. After `SACP_METRICS_SESSION_GRACE_S` seconds (default 30), `evict_session(session_id)` is called, which removes all label combinations for that session from every session-scoped metric family. Eviction is logged at DEBUG level.

The grace window allows a final Prometheus scrape to capture the terminal counter values before the series disappear from the registry (SC-003).
