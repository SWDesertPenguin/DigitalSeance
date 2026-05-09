# Contract: network rate-limit audit events

Two new `action` strings written to `admin_audit_log` (no schema change). Cross-ref [data-model.md](../data-model.md#entities) for the row-level field semantics.

## `network_rate_limit_rejected`

**When**: the per-IP rate-limit middleware rejects a non-exempt inbound request because the source IP's token-bucket budget is exhausted. Per FR-009, the row is NOT written per-rejection — it is written by the background coalescing flush task once per `(source_ip_keyed, minute_bucket)`. The metrics counter `sacp_rate_limit_rejection_total` increments per-rejection (cross-ref [metrics.md](./metrics.md)) so per-rejection durability survives via Prometheus scrape.

**Row contract**:
- `action = "network_rate_limit_rejected"` (literal string).
- `target_id` is `source_ip_keyed` — the limiter's keying form (full IPv4 dotted-decimal at /32, OR canonical hex `/64` IPv6 prefix). MUST NOT be the raw IPv6 host address; that is the entire reason for the keying transform.
- `previous_value` is `null`. The limiter has no "previous state" semantics for rejections.
- `new_value` is a JSON object with these keys:
  - `minute_bucket: int` — `floor(rejected_at_epoch / 60)`; identifies the coalescing window. Operators can derive the human-readable minute via `datetime.fromtimestamp(minute_bucket * 60, UTC)`.
  - `first_rejected_at: ISO 8601 string` — earliest rejection in the window.
  - `last_rejected_at: ISO 8601 string` — latest rejection in the window.
  - `rejection_count: int` — number of rejections coalesced into this row (always >= 1).
  - `endpoint_paths_seen: list[str]` — distinct paths rejected within the window. PATH ONLY (no query string). Capped at a small N to bound row size; if more distinct paths were rejected than the cap, the list is truncated and a `paths_truncated: true` flag is added.
  - `methods_seen: list[str]` — distinct HTTP methods rejected within the window.
  - `limiter_window_remaining_s: float | null` — informational; seconds until the limiter would admit the next request from this IP at the time of the latest rejection. May be `null` if the bookkeeping was unavailable at flush time.

**Sequencing**: written by the background flush task, NOT in the request path. The request path increments an in-memory counter and returns HTTP 429 immediately. If the flush task fails, the row is lost for that minute but the metrics counter retains per-rejection durability.

**Privacy contract** (SC-009): the row MUST NOT include the rejected request's headers, query string, or body content. Implementation MUST strip query strings before adding to `endpoint_paths_seen`. CI's privacy contract test (`test_019_audit_and_metrics.py`) asserts the row shape.

## `source_ip_unresolvable`

**When**: the middleware cannot determine a source IP for an inbound request. Per FR-012, the request is rejected with HTTP 400 and one audit row is written. NOT coalesced — these are individually rare and forensically important.

**Row contract**:
- `action = "source_ip_unresolvable"` (literal string).
- `target_id` is `null`. There is no IP to attribute to — that is the entire condition this event captures.
- `previous_value` is `null`.
- `new_value` is a JSON object with these keys:
  - `rejected_at: ISO 8601 string` — wall-clock time of the rejection.
  - `request_path: str` — path-only, no query string.
  - `request_method: str` — HTTP method (e.g., `"GET"`, `"POST"`).
  - `reason: str` — one of:
    - `"no_peer"` — the framework reported no peer IP (malformed connection).
    - `"malformed_forwarded_header"` — `_TRUST_FORWARDED_HEADERS=true` and the `Forwarded` header could not be parsed.
    - `"no_xff_when_trust_enabled"` — `_TRUST_FORWARDED_HEADERS=true` and neither `Forwarded` nor `X-Forwarded-For` was present.
    - `"parse_error"` — catch-all for unexpected `ipaddress` library failures (e.g., a value that passed earlier checks but failed final parsing).

**Sequencing**: written BEFORE the HTTP 400 response is returned. Failure to write the row does NOT cause the request to fall through (the 400 still goes out); the audit-write failure is logged via the existing audit-failure path.

**Idempotency**: the middleware emits one row per unresolvable request. Operators investigating a flood of `source_ip_unresolvable` rows should look upstream (proxy misconfiguration, malformed inbound traffic) — high volume here usually indicates a configuration drift, not an attack.

## Cross-cutting

- Both events are append-only via the existing `admin_audit_log` path (V9 log integrity).
- Both are visible in operator-facing log queries; no separate UI surface in Phase 1 (Web UI rendering is a follow-up if operators ask for it; spec 011 is unchanged by this spec).
- `session_id` and `facilitator_id` on every row carry the literal sentinel string `"__network_layer__"`. These are infrastructure-tier events with no session or facilitator context (the limiter runs pre-auth), but `admin_audit_log`'s schema requires NOT NULL on those columns. The sentinel is the v1 implementation contract; downstream audit consumers (e.g., spec 029's audit-log viewer) MUST detect the sentinel and label such rows as "Network layer (pre-auth)" rather than dereferencing it as a real session or facilitator id. See [research.md §"Network-layer audit row identity"](../research.md) for the rationale (no schema migration in v1).
- Both events are emitted only when `SACP_NETWORK_RATELIMIT_ENABLED=true`. When the master switch is off, the middleware is not registered and no rows of either action are emitted (SC-006).
