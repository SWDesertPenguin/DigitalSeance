# Contract: spec 016 metrics surface — `sacp_rate_limit_rejection_total`

**Branch**: `019-network-rate-limiting` | **Source**: spec FR-010, SC-009 | **Date**: 2026-05-08

This spec extends spec 016's existing Prometheus counter `sacp_rate_limit_rejection_total` with a label set that distinguishes network-layer rejections from any future application-layer rejections that may share the counter. The contract specifies: (1) the label set, (2) the cardinality bound, (3) the privacy contract (what MUST NOT appear in labels), and (4) the test signature that proves it.

---

## Label set

The counter `sacp_rate_limit_rejection_total` carries exactly two labels for this spec's emissions:

| Label | Type | Values | Source |
|---|---|---|---|
| `endpoint_class` | string enum | `"network_per_ip"` (this spec) | FR-010 |
| `exempt_match` | string boolean | `"false"` (this spec always emits with false; exempt paths bypass the limiter entirely and never increment) | FR-010, FR-006 |

### Example metric line

```text
# HELP sacp_rate_limit_rejection_total Rate-limit rejections by class
# TYPE sacp_rate_limit_rejection_total counter
sacp_rate_limit_rejection_total{endpoint_class="network_per_ip",exempt_match="false"} 142
```

### Future label values (forward-compatible)

The label set is designed so the existing §7.5 application-layer per-participant limiter can adopt the same counter without spec amendment. When that lands, additional series will appear:

```text
sacp_rate_limit_rejection_total{endpoint_class="app_layer_per_participant",exempt_match="false"} 87
```

Spec 019 does NOT emit `endpoint_class="app_layer_per_participant"`. That value is reserved for §7.5 to use when it adopts the counter.

The `exempt_match` label exists to flag cases where a future variant of the limiter rejects on a path that matched the exempt set (currently impossible for spec 019 because exempt paths bypass the limiter; included for forward-compatibility with operator-configurable exempt sets in v2+).

---

## Cardinality bound

This spec contributes exactly **1** new time series to the counter:

- `(endpoint_class="network_per_ip", exempt_match="false")` — the only label combination this spec emits.

Total counter cardinality across all current emitters is bounded above by `2 (endpoint_class values) × 2 (exempt_match values) = 4` series. This is well within Prometheus's per-counter cardinality budget and is unaffected by traffic volume.

---

## Privacy contract (SC-009)

The counter labels MUST NOT include any of:

- **Source IP** (raw or keyed). The audit log carries `source_ip_keyed` (cross-ref [audit-events.md](./audit-events.md)); the metric does NOT.
- **Endpoint path** (full or partial). The audit log's coalesced row carries `endpoint_paths_seen`; the metric does NOT.
- **Query string** in any form.
- **Request headers** in any form.
- **Request body content** in any form.
- **User-Agent**, **Authorization** (or any sub-form like first 8 chars of a token), or any auth-related field.
- **Participant ID, session ID, or any application-layer identifier** — those are §7.5's concern and must not bleed into the network-layer label set even when §7.5 adopts the counter.

The privacy contract test (`test_019_audit_and_metrics.py`) MUST assert the label set is exactly `{endpoint_class, exempt_match}` and reject any addition.

---

## Increment semantics

### Per-rejection

The counter increments **per-rejection**, NOT per-coalesced-audit-row (FR-010 / FR-009 distinction). A flood of 200 rejections from one IP within one minute increments the counter 200 times AND writes one audit row with `rejection_count=200`. The two surfaces serve different purposes:
- Metric counter: per-rejection durability across orchestrator restarts via Prometheus scrape (15-second cadence).
- Audit log: forensic record of which IPs hit the limiter, with operator-queryable structure.

### Source-IP-unresolvable rejections

When the middleware rejects with HTTP 400 because source IP cannot be determined (FR-012), the counter MUST increment with `(endpoint_class="network_per_ip", exempt_match="false")` — same labels as a normal rejection. The fact that source IP was unresolvable surfaces in the audit log row's `reason` field (cross-ref [audit-events.md `source_ip_unresolvable`](./audit-events.md#source_ip_unresolvable)), not in the metric labels. This keeps cardinality bounded.

### What does NOT increment the counter

- Exempt-path requests (`GET /health`, `GET /metrics`) — the limiter middleware bypasses these entirely; no rejection, no counter increment.
- Requests admitted by the limiter that subsequently fail auth — the limiter only sees them at the rate-limit decision, which was "admit." Auth failure is a separate metric surface (out of scope for this spec).
- Requests that arrive when `SACP_NETWORK_RATELIMIT_ENABLED=false` — the middleware is not registered (per [middleware-ordering.md](./middleware-ordering.md)); no counter increment is possible.

---

## Test signature

A test in `tests/test_019_audit_and_metrics.py` MUST assert (sketch):

```python
def test_rejection_increments_counter_with_correct_labels(client, registry):
    """FR-010: rejections increment sacp_rate_limit_rejection_total with
    endpoint_class='network_per_ip', exempt_match='false'."""
    # Drive the limiter to its threshold from one IP
    drive_flood(client, source_ip="203.0.113.5", count=200)

    metric = registry.get_sample_value(
        "sacp_rate_limit_rejection_total",
        labels={"endpoint_class": "network_per_ip", "exempt_match": "false"},
    )
    assert metric is not None and metric > 0


def test_counter_labels_carry_no_pii(registry):
    """SC-009: the counter MUST NOT include source IP, query string,
    headers, or body content in any label."""
    metric_family = registry.get_sample_family("sacp_rate_limit_rejection_total")
    for sample in metric_family.samples:
        forbidden = {"source_ip", "ip", "client_ip", "path", "query", "header", "body", "user_agent"}
        assert not (set(sample.labels.keys()) & forbidden), (
            f"SC-009 violated: forbidden label key in {sample.labels}"
        )
        assert set(sample.labels.keys()) == {"endpoint_class", "exempt_match"}, (
            f"unexpected labels: {sample.labels}"
        )
```

---

## Cross-spec references

- **Spec 016 (prometheus-metrics) FR-002** — defines `/metrics` exempt path and the existing counter surface this spec extends.
- **Spec 016 §"Counters"** (or the equivalent section in spec 016's contracts) — defines the counter name `sacp_rate_limit_rejection_total`. This spec does not rename or move the counter; it adds two labels.
- **Cross-ref [audit-events.md](./audit-events.md)** — the per-rejection vs per-(IP, minute) distinction between the metric counter and the audit log.
- **Cross-ref [middleware-ordering.md](./middleware-ordering.md)** — the exempt-path bypass that ensures `/health` and `/metrics` never increment the counter.
