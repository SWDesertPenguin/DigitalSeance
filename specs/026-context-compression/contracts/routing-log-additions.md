# Contract: `routing_log.reason` Enum Additions

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec FR**: FR-003, FR-018, FR-020 | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md §12](../research.md)

Spec 026 adds five new values to the `routing_log.reason` application-level enum. `routing_log.reason` is a TEXT column (NOT a Postgres enum type), so this is an application-level extension — no migration required.

## New `reason` values

| Value | Emitted at | Source FR | Notes |
|---|---|---|---|
| `cache_hit` | `src/api_bridge/caching.py` — response-handling site after a successful LiteLLM call where the provider response indicates a cache hit. | FR-003 | Payload extension: `cached_prefix_tokens` (integer) in the routing_log per-stage details column. |
| `cache_miss` | Same site, when no cache hit. | FR-003 | Payload extension: none beyond the standard fields. |
| `compression_applied` | `src/compression/service.py` — after a successful non-NoOp `compress(...)` returns. | FR-003 | Payload extension: `compressor_id` + `source_tokens` + `output_tokens` for the per-dispatch summary. |
| `compression_pipeline_error` | `src/compression/service.py` — catch-handler around any Compressor exception. The dispatch path then falls through to un-compressed dispatch per FR-020. | FR-020 | Payload extension: `compressor_id` + `error_class` (the exception's class name) + truncated message. |
| `density_anomaly_flagged` | `src/orchestrator/density.py` — per-turn dual-write alongside the existing `convergence_log` write per Session 2026-05-11 §4. | FR-018 | Payload extension: `density_value` (float) + `baseline_mean` (float) + `ratio` (float). |

## Co-commit invariant (FR-018 + Session 2026-05-11 §4)

The `density_anomaly_flagged` dual-write to `routing_log` AND `convergence_log` MUST happen in the same per-turn database transaction. Implementation: the existing per-turn transaction in `src/orchestrator/loop.py` wraps both writes. Failure of either fails the whole transaction; partial-write recovery is NOT required because both target append-only tables in the same database.

## Emission-site mapping

```text
[src/api_bridge/caching.py]
    ↓ on dispatch response with cache hit
    → routing_log.reason = 'cache_hit'  + cached_prefix_tokens
    ↓ on dispatch response without cache hit
    → routing_log.reason = 'cache_miss'

[src/compression/service.py — compress(...)]
    ↓ on NoOp completion
    → (no routing_log emission on the compression axis; the dispatch itself is byte-identical to baseline)
    ↓ on non-NoOp success
    → routing_log.reason = 'compression_applied' + compressor_id + source_tokens + output_tokens
    ↓ on any Compressor exception
    → routing_log.reason = 'compression_pipeline_error' + compressor_id + error_class
    → fall through to un-compressed dispatch (FR-020)

[src/orchestrator/density.py]
    ↓ on density signal fire
    → convergence_log INSERT with tier='density_anomaly' (existing spec 004 path)
    → routing_log.reason = 'density_anomaly_flagged' + density_value + baseline_mean + ratio
    (both writes co-commit in same transaction per Session 2026-05-11 §4)
```

## Backward compatibility

Existing routing_log readers (spec 010 debug-export, spec 016 metrics, spec 022 detection-event surface) MUST handle the five new `reason` values without crashing. Spec 022 specifically — its event-class registry does NOT include `density_anomaly_flagged` because the panel surfaces `density_anomaly` from `convergence_log` (the canonical signal), not the routing_log marker. The marker is for the routing audit trail, not for the detection-event panel.

Spec 010's debug-export emits all routing_log rows verbatim — no schema knowledge needed.

Spec 016 metrics may want to graph cache_hit_rate (cache_hit / (cache_hit + cache_miss)) and density_anomaly_rate as separate metrics. Tasks T0XX adds the metric definitions.

## Cross-reference

- The compression telemetry per-dispatch is in `compression_log` (separate table; see [compression-log-row.md](./compression-log-row.md)). Routing_log carries the per-turn audit-trail markers; compression_log carries the per-dispatch structured row.
- The Session 2026-05-11 §4 dual-write is the architectural decision pinning the two-write pattern.
