# Contract: GET /metrics Endpoint

## Overview

The `/metrics` endpoint exposes Prometheus-format operational metrics for the SACP orchestrator. It is a pull endpoint: the deployer configures an external Prometheus-compatible scraper to poll it at a configured interval.

## Request

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/metrics` (or the path configured in `SACP_METRICS_BIND_PATH`) |
| Auth | None required at the application layer. Access control is the deployer's responsibility via network policy (same model as `/health`). |
| Parameters | None |

## Response (enabled)

| Field | Value |
|---|---|
| HTTP status | 200 OK |
| Content-Type | `text/plain; version=0.0.4; charset=utf-8` |
| Body | Prometheus text format (one metric family block per metric, `# HELP` + `# TYPE` headers, label sets, values) |
| Format version | Prometheus text format 0.0.4 (not OpenMetrics) |

## Response (disabled)

When `SACP_METRICS_ENABLED` is unset or `false`, the route is NOT registered. Any request to `/metrics` returns HTTP 404 from route absence (not a 404 from a registered handler).

## Rate-Limit Exemption

The path `("GET", "/metrics")` is included in `EXEMPT_PATHS` in `src/middleware/network_rate_limit.py`. Scrapes from a configured Prometheus instance are exempt from the per-IP token-bucket rate limiter and do not count toward any participant's rate-limit budget (FR-002, SC-008).

## Privacy Contract

No metric label may carry: message content, system prompt content, API key material, model name, IP address, user-agent string, or request URL. `participant_id_hash` uses the first 8 hex chars of SHA-256(participant_id) — non-reversible within the metric surface (FR-004, SC-007).

## Performance Contract

Response time P95 <= 500ms for a deployment of 100 sessions x 5 participants. Response time is O(active_series). No database reads on the hot path (FR-014).

## Metric Format (example)

```
# HELP sacp_participant_tokens_total Provider token usage per session participant and direction
# TYPE sacp_participant_tokens_total counter
sacp_participant_tokens_total{session_id="abc123",participant_id_hash="1a2b3c4d",direction="prompt"} 1250.0
sacp_participant_tokens_total{session_id="abc123",participant_id_hash="1a2b3c4d",direction="completion"} 3400.0
# HELP sacp_provider_request_total Provider dispatch requests by kind and outcome
# TYPE sacp_provider_request_total counter
sacp_provider_request_total{provider_kind="litellm",outcome="success"} 42.0
sacp_provider_request_total{provider_kind="litellm",outcome="error_5xx"} 3.0
```
