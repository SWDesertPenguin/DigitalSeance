# SACP Metrics Catalog

Authoritative reference for every metric family exposed by the SACP Prometheus endpoint. Per spec 016 FR-013, this document MUST enumerate every metric, its labels, the bounded enumerations for each label, and the cardinality bound.

The `/metrics` endpoint is enabled by `SACP_METRICS_ENABLED=true`. When disabled (the default), no endpoint is registered and no metric collection overhead occurs.

## Metric families

### `sacp_rate_limit_rejection_total`

| Field | Value |
|---|---|
| Type | Counter |
| Description | Rate-limit rejections by class |
| Labels | `endpoint_class`, `exempt_match` |
| `endpoint_class` values | `network_per_ip`, `app_layer_per_participant` |
| `exempt_match` values | `true`, `false` |
| Cardinality bound | 4 series maximum |
| Session-scoped | No (never evicted) |
| Source spec | 019 rejection path; 016 FR-011 |

### `sacp_participant_tokens_total`

| Field | Value |
|---|---|
| Type | Counter |
| Description | Provider token usage per session participant and direction |
| Labels | `session_id`, `participant_id_hash`, `direction` |
| `direction` values | `prompt`, `completion` |
| `participant_id_hash` | First 8 hex chars of SHA-256(participant_id) — privacy-safe, non-reversible |
| Cardinality bound | active_sessions x participants_per_session x 2 |
| Session-scoped | Yes — evicted within `SACP_METRICS_SESSION_GRACE_S` after session end |
| Source spec | 016 FR-008; sourced from `response.input_tokens` / `response.output_tokens` in loop.py `_log_usage()` |

### `sacp_participant_cost_usd_total`

| Field | Value |
|---|---|
| Type | Counter |
| Description | Provider cost in USD per session participant |
| Labels | `session_id`, `participant_id_hash` |
| Cardinality bound | active_sessions x participants_per_session |
| Session-scoped | Yes |
| Source spec | 016 FR-008; sourced from `response.cost_usd` in loop.py `_log_usage()` |

### `sacp_provider_request_total`

| Field | Value |
|---|---|
| Type | Counter |
| Description | Provider dispatch requests by kind and outcome |
| Labels | `provider_kind`, `outcome` |
| `provider_kind` values | `litellm`, `mock`, `other` |
| `outcome` values | `success`, `error_5xx`, `error_4xx`, `timeout`, `auth_error`, `rate_limit`, `circuit_open` |
| Cardinality bound | 3 x 7 = 21 series maximum |
| Session-scoped | No |
| Source spec | 016 FR-008; sourced from dispatch success/failure path in loop.py |

### `sacp_session_convergence_similarity`

| Field | Value |
|---|---|
| Type | Gauge |
| Description | Last convergence similarity score for a session (0.0=diverged, 1.0=converged) |
| Labels | `session_id` |
| Value range | 0.0 to 1.0 |
| Sentinel | Series absent when no similarity score has been produced (session below spec 004 minimum sample threshold). The gauge MUST NOT report a misleading default like 0 or 1 for cold sessions. |
| Cardinality bound | active_sessions |
| Session-scoped | Yes |
| Source spec | 016 FR-009; sourced from spec 004 convergence engine via `_compute_turn_delay()` in loop.py |

### `sacp_routing_decision_total`

| Field | Value |
|---|---|
| Type | Counter |
| Description | Routing decisions per session and decision class |
| Labels | `session_id`, `routing_mode`, `skip_reason` |
| `routing_mode` values | decision action strings from spec 003 routing engine (e.g., `dispatched`, `skipped`, `burst_accumulating`, `review_gated`, `phase_transition`) |
| `skip_reason` values | `""` (dispatched, no skip), `circuit_open`, `budget_exceeded`, `skipped` |
| Cardinality bound | active_sessions x routing_mode_values x skip_reason_values |
| Session-scoped | Yes |
| Source spec | 016 FR-010; sourced from `_log_routing()` and `_log_skip_entry()` in loop.py |

## Privacy contract

Per spec 016 FR-004, no metric label may carry: message content, system prompt content, API key material or fingerprint, model name, IP address, user-agent string, or request URL. `participant_id_hash` uses a one-way hash (SHA-256, 8 hex chars) of the participant UUID; the raw UUID is never exposed in labels.

## Cardinality management

Session-scoped metric series are evicted from the registry within `SACP_METRICS_SESSION_GRACE_S` seconds after a session ends. The grace window allows one final Prometheus scrape to capture terminal counter values. After eviction, the series are absent from subsequent scrapes.

For a deployment running 1000 sessions over 24 hours with a default 30-second grace window, the steady-state series count is bounded by the number of concurrently-active sessions, not the total sessions ever created.
