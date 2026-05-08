# Quickstart: Network-Layer Per-IP Rate Limiting

**Branch**: `019-network-rate-limiting` | **Date**: 2026-05-08 | **Plan**: [plan.md](./plan.md)

Operator workflow for opting into per-IP rate limiting on the MCP server (port 8750). Default behavior with no configuration is unchanged from pre-feature: no middleware registered, no rejections, no audit entries. The limiter is strictly opt-in (SC-006). There is no facilitator workflow — this is operator-tier infrastructure with no per-session controls.

---

## Operator workflow

### Enable the limiter

Edit the `.env` file used by the Dockge stack at `/mnt/.ix-apps/app_mounts/dockge/stacks/sacp/.env`:

```bash
# Master switch — must be 'true' to register the middleware
SACP_NETWORK_RATELIMIT_ENABLED=true

# Steady-state requests per minute per source IP (default 60)
SACP_NETWORK_RATELIMIT_RPM=60

# Burst capacity (default 15 = RPM/4, allowing ~15-second bursts)
SACP_NETWORK_RATELIMIT_BURST=15

# Trust X-Forwarded-For / Forwarded headers (default false; immediate peer IP only)
# Set to 'true' ONLY if a trusted reverse proxy fronts the orchestrator AND that proxy
# sanitizes upstream-supplied headers before forwarding.
SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=false

# LRU bound on the per-IP budget map (default 100000, range [1024, 1000000])
SACP_NETWORK_RATELIMIT_MAX_KEYS=100000
```

Restart the orchestrator stack from Dockge. Verify config validation passes:

```bash
docker compose logs sacp-orchestrator | grep -iE "config validation|network_ratelimit"
# Expected: "Config validation: 5 SACP_NETWORK_RATELIMIT_* validators passed"
```

If any value is out of range, the orchestrator process exits at startup before binding ports (V16 fail-closed). The error message names the offending variable.

### Verify middleware registration order

The limiter MUST be the first middleware on the request stack (FR-001 / FR-002). After restart, the startup-test signature is exercised by CI; locally you can confirm via the orchestrator's middleware-introspection log line:

```bash
docker compose logs sacp-orchestrator | grep -i "middleware order"
# Expected: "Middleware order (outermost first): NetworkRateLimit, ..."
```

If `NetworkRateLimit` is not listed first, the ordering contract is broken. File an issue immediately — auth/bcrypt would run before the limiter, defeating the threat model.

---

## Observe limiter behavior

### Watch routing_log middleware-duration sample

The limiter samples its own per-request overhead into `routing_log` (spec 003 §FR-030). Tail recent rows:

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT at, payload->>'middleware' AS mw, payload->>'duration_ms' AS dur_ms FROM routing_log WHERE payload->>'middleware' = 'NetworkRateLimit' ORDER BY at DESC LIMIT 20;"
```

Expected: `dur_ms` values in the sub-millisecond to low-millisecond range, well below the V14 per-stage budget tolerance.

### Verify Retry-After header on a synthetic flood

Drive a flood of requests against a non-exempt MCP endpoint from a single source IP. The simplest reproducer is curl in a loop:

```bash
# From a host with a single source IP, hit the MCP server's auth endpoint at high rate
for i in $(seq 1 200); do
  curl -s -o /dev/null -w "%{http_code} %{header_retry_after}\n" \
    -X POST "https://sacp.local:8750/mcp/tool" \
    -H "Authorization: Bearer invalid-token-$i" \
    -H "Content-Type: application/json" \
    -d '{"name":"some_tool","arguments":{}}' &
done
wait
```

Expected output sequence: roughly the first `BURST` requests return 401 (auth failure with valid limiter pass-through). Subsequent requests return `429` with a `Retry-After` header indicating seconds until the limiter would admit the next request:

```text
401
401
401
... (~15 401s — burst capacity)
429 1
429 1
429 2
... (140+ 429s with increasing Retry-After)
```

The limiter is doing its job: bcrypt is invoked at most `RPM` times per minute (= 60 by default) regardless of the flood rate.

### Audit-log query for rejection rows

Per FR-009, the audit logger coalesces rejections into per-`(source_ip_keyed, minute)` summary rows. After a flood, query:

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT at, target_id AS source_ip_keyed, new_value->>'rejection_count' AS count, new_value->'endpoint_paths_seen' AS paths FROM admin_audit_log WHERE action = 'network_rate_limit_rejected' ORDER BY at DESC LIMIT 10;"
```

Expected: one row per `(source_ip_keyed, minute_bucket)` with `rejection_count` summing all rejections in that minute. Sustained 1-hour flood from a single IP produces 60 rows (one per minute) rather than thousands.

For source-IP-unresolvable rejections (FR-012):

```bash
docker compose exec sacp-postgres psql -U sacp -d sacp -c \
  "SELECT at, new_value->>'reason' AS reason, new_value->>'request_path' AS path, new_value->>'request_method' AS method FROM admin_audit_log WHERE action = 'source_ip_unresolvable' ORDER BY at DESC LIMIT 10;"
```

These rows are NOT coalesced — they're individually rare and forensically important.

### Metrics surface

The Prometheus counter `sacp_rate_limit_rejection_total` increments per-rejection (not per-coalesced-row). Scrape `/metrics` and look for:

```text
# HELP sacp_rate_limit_rejection_total Rate-limit rejections by class
# TYPE sacp_rate_limit_rejection_total counter
sacp_rate_limit_rejection_total{endpoint_class="network_per_ip",exempt_match="false"} 142
```

The metric is the durable per-rejection record across orchestrator restarts (audit coalescing flushes once per minute; metrics scrape every 15 seconds via Prometheus).

---

## Confirm exempt paths stay reachable under load

Drive `/health` and `/metrics` at high rate from the same source IP whose budget is exhausted:

```bash
# Same IP A is being rejected on /mcp/tool — confirm /health and /metrics still serve
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{http_code}\n" "https://sacp.local:8750/health"
done | sort | uniq -c
# Expected: "100 200" — no 429s, regardless of IP A's per-IP budget state.
```

If `/health` returns 429, the exempt-path check has regressed. File an issue.

---

## Disabling / rollback

### Disable the limiter

```bash
# In the .env file, either remove the var or set explicitly to false
SACP_NETWORK_RATELIMIT_ENABLED=false
```

Restart the orchestrator. The middleware is no longer registered; behavior reverts byte-identically to pre-feature (SC-006). No audit-log entries for `network_rate_limit_rejected` are emitted from this point.

### Tune the limit

If the default `RPM=60` is too aggressive for your traffic pattern (e.g., legitimate clients hitting 80 RPM during normal use), raise it:

```bash
SACP_NETWORK_RATELIMIT_RPM=120
SACP_NETWORK_RATELIMIT_BURST=30  # keep BURST = RPM/4
```

Restart. New limit is in effect immediately; existing per-IP buckets are reset (in-memory state does not survive restart by design).

If many legitimate clients share an IP (NAT, corporate proxy), consider raising `RPM` further or — when behind a trusted proxy — enabling `_TRUST_FORWARDED_HEADERS=true` so per-client keying works. Per-shared-IP traffic remains a known limitation of per-IP limiting; future amendments may introduce per-token / per-fingerprint layers.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Legitimate clients hitting 429 unexpectedly | `RPM` too low for traffic pattern | Raise `SACP_NETWORK_RATELIMIT_RPM`; confirm with audit-log `rejection_count` per IP. |
| All clients behind a proxy share one budget | `_TRUST_FORWARDED_HEADERS=false` (default) — limiter sees the proxy IP only | Set to `true` AFTER confirming the proxy sanitizes upstream-supplied `X-Forwarded-For` / `Forwarded` headers. |
| Rejection counter increments but no audit rows appear | Background flush task crashed; or audit-write path has a transient error | Check orchestrator logs for "audit_flush_failed"; the metric counter remains accurate. |
| `source_ip_unresolvable` rows appear without explanation | Malformed inbound traffic (raw socket anomalies) OR `_TRUST_FORWARDED_HEADERS=true` with a proxy not setting the expected header | Inspect `new_value->>'reason'` field; if `no_xff_when_trust_enabled`, fix the proxy. |
| `routing_log` middleware-duration samples show high values | `MAX_KEYS` set too low forcing constant LRU evictions; or unbounded keying explosion (consider raising `MAX_KEYS`) | Raise `SACP_NETWORK_RATELIMIT_MAX_KEYS` toward the upper bound (1_000_000). |
| Orchestrator exits at startup with `ConfigValidationError: SACP_NETWORK_RATELIMIT_*` | One env var has an out-of-range value | Read the startup error — it names the offending var. Fix and restart. |
| Test `test_019_middleware_order.py` fails | Some middleware was registered before NetworkRateLimit | The FR-002 startup-test caught a regression. Inspect `src/main.py` middleware-registration order. |
