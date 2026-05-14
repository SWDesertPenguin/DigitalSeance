# Research: Prometheus-Format Metrics (spec 016)

## §1 — prometheus_client vs custom implementation

**Decision**: use `prometheus_client` (the official Python Prometheus client library).

Rationale: `prometheus_client` provides a stable, well-tested API for Counter, Gauge, and CollectorRegistry; it generates Prometheus text format (MIME type `text/plain; version=0.0.4`) natively via `generate_latest()`; it is the de-facto standard for Python services and carries no additional transitive dependencies beyond the standard library. The pre-016 stub in `src/observability/metrics.py` was always intended as a placeholder until this spec landed (see stub docstring). Alternative considered: a hand-rolled text serializer. Rejected because it would duplicate format compliance testing, drift from the Prometheus spec, and provide no advantage over the battle-tested library.

**Version**: `prometheus-client==0.25.0` (latest stable as of 2026-05-13, per `pip index versions prometheus-client`). Pinned to an exact minor version per Constitution §6.3.

## §2 — Session-scoped cardinality and label contract

The label cardinality contract bounds the maximum number of active time series to:

```
active_sessions x max_participants x per_session_metric_families
```

Labels used across the 6 metric families:

| Label | Type | Bounded? | Values |
|---|---|---|---|
| `session_id` | string (UUID) | Yes — by active session count | UUID v4 |
| `participant_id_hash` | string | Yes — by participants per session | first 8 hex chars of SHA-256(participant_id) |
| `direction` | enum | Yes | `prompt`, `completion` |
| `provider_kind` | enum | Yes | `litellm`, `mock` |
| `outcome` | enum | Yes | `success`, `error_5xx`, `error_4xx`, `timeout`, `auth_error`, `rate_limit`, `circuit_open` |
| `routing_mode` | enum | Yes | derived from routing decision action field; see spec 003 |
| `skip_reason` | enum | Yes | `""`, `circuit_open`, `budget_exceeded`, `skipped` |
| `endpoint_class` | enum | Yes | `network_per_ip`, `app_layer_per_participant` |
| `exempt_match` | string bool | Yes | `true`, `false` |

Labels explicitly excluded (FR-004): model name, API key material or fingerprint, message content, system prompt content, IP address, user-agent string, request URL.

`participant_id_hash` design: first 8 hex chars of `hashlib.sha256(participant_id.encode()).hexdigest()`. This is privacy-safe (non-reversible for practical purposes in the metric context), still useful for correlating per-participant signals within a session (same participant always maps to same hash within a deployment lifetime), and avoids exposing the raw participant UUID in the metrics output. The full participant_id is available to the facilitator via the audit log for any investigation that needs it.

## §3 — Eviction strategy

**Problem**: session-scoped labels (`session_id`, `participant_id_hash`) must be evicted when a session ends to bound cardinality over long-running deployments.

**Approach**: use a per-session tracking dict in a dedicated `MetricsEvictionTracker`. Each session that has metric series registered is added to the tracker on first increment. On session end, the caller invokes `evict_session(session_id)`, which iterates over all metric families that carry `session_id` labels and calls `.remove(session_id=session_id, ...)` for each known label combination. The eviction is scheduled after `SACP_METRICS_SESSION_GRACE_S` seconds (default 30) to allow a final Prometheus scrape to capture terminal counter values before the series disappear.

`prometheus_client.Counter` and `prometheus_client.Gauge` expose a `.remove(*labelvalues)` method that removes a specific labeled child from the internal registry. This is the correct mechanism; `prometheus_client`'s `CollectorRegistry` does not provide bulk-removal by partial label match, so the tracker must remember the full label tuples for each session.

**Grace window**: default 30 seconds (one standard scrape interval). Configurable via `SACP_METRICS_SESSION_GRACE_S` in [5, 300]. The eviction fires via `asyncio.get_event_loop().call_later()` from the session-end hook.

## §4 — /metrics endpoint integration

The `/metrics` endpoint mounts on the existing `mcp_server` FastAPI app (port 8750) as a conditional router, following the same pattern as spec 029's audit viewer and spec 022's detection event history. The endpoint is gated by `SACP_METRICS_ENABLED=true`; when false/unset, the router is not included and the endpoint returns HTTP 404 from route absence.

Rate-limit exemption: `EXEMPT_PATHS` in `src/middleware/network_rate_limit.py` already includes `("GET", "/metrics")` (this was added in spec 019 as a forward reference). No change needed to the middleware.

The response uses `generate_latest(REGISTRY)` from `prometheus_client` and the `CONTENT_TYPE_LATEST` constant for the correct MIME type.

## §5 — Migration from pre-016 stub

The pre-016 stub in `src/observability/metrics.py` exports:
- `sacp_rate_limit_rejection_total` — a `_CounterFamily` instance
- `increment_network_rate_limit_rejection()` — wrapper
- `reset_for_tests()` — test helper
- `get_circuit_breaker_metrics()` — reads from circuit_breaker module
- `CircuitBreakerMetrics`, `MetricSample` dataclasses

The spec 019 tests (`test_019_us3_audit_metrics.py`) call:
- `sacp_rate_limit_rejection_total.labels(endpoint_class=..., exempt_match=...).inc()` (via `increment_network_rate_limit_rejection`)
- `sacp_rate_limit_rejection_total.get_sample_value({...})` — returns float or None
- `sacp_rate_limit_rejection_total.samples()` — returns iterator of MetricSample
- `reset_for_tests()` — discards all counter values

The migration strategy: replace `_CounterFamily` internals with a real `prometheus_client.Counter` backed by a private `CollectorRegistry` (REGISTRY). Add adapter wrappers that translate the existing call surface:
- `labels(**kw).inc()` — delegates to `_counter.labels(**kw).inc()`
- `get_sample_value(labels)` — reads from `REGISTRY.get_sample_value(metric_name, labels)`
- `samples()` — iterates collected samples from REGISTRY
- `reset()` / `reset_for_tests()` — removes and re-creates the Counter on the REGISTRY

This preserves the exact call surface while backing it with real prometheus_client internals.

The `_assert_labels` privacy guard from the pre-016 stub must be preserved: the spec 019 contract tests explicitly verify that `ValueError` is raised for unknown label keys and out-of-set label values. This guard lives in the new wrapper layer.
