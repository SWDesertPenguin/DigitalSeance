# Data Model: Network-Layer Per-IP Rate Limiting

**Branch**: `019-network-rate-limiting` | **Date**: 2026-05-08 | **Plan**: [plan.md](./plan.md)

Captures entities and module-level shapes derived from [spec.md](./spec.md) and [research.md](./research.md). This feature introduces NO database tables, NO alembic migration, and NO `tests/conftest.py` schema-mirror change — all entities are in-memory or audit-log row shapes that ride the existing `admin_audit_log` table without schema delta.

---

## Schema additions

**None.** The limiter is in-memory only (research.md §3, §6). Rejection audit rows write to the existing `admin_audit_log` table via the established append-only path (Constitution V9). No new columns. No migration. No conftest mirror update.

---

## Entities

### `PerIPBudget` (process-scope, in-memory)

The token-bucket state per source-IP keyed form. Entries live in an `OrderedDict[str, PerIPBudget]` bounded by `SACP_NETWORK_RATELIMIT_MAX_KEYS` with LRU eviction (research.md §3).

```python
@dataclass
class PerIPBudget:
    source_ip_keyed: str          # IPv4 dotted-decimal at /32, OR IPv6 /64 prefix in canonical hex form
    current_tokens: float         # remaining budget; refilled lazily on each access
    last_refill_at: float         # monotonic timestamp (seconds) of the last refill computation
```

**State transitions**:
- **Created** on first request from a previously-unseen `source_ip_keyed`. Initial `current_tokens = BURST` (full bucket); `last_refill_at = now()`.
- **Accessed** on every non-exempt request:
  1. `refill = (now - last_refill_at) × RPM / 60.0`
  2. `current_tokens = min(BURST, current_tokens + refill)`
  3. `last_refill_at = now`
  4. If `current_tokens >= 1`, decrement and admit. Otherwise, reject (HTTP 429 + Retry-After + audit + metric).
  5. Move-to-end of `OrderedDict` (LRU recency).
- **Evicted** when the map size exceeds `MAX_KEYS`: `OrderedDict.popitem(last=False)` removes the least-recently-accessed entry. An evicted IP returning later starts fresh with a full bucket.

**Memory bound**: `MAX_KEYS × sizeof(PerIPBudget)`. With `MAX_KEYS=100_000` (default) and ~300 bytes per entry including dict overhead, worst-case map size is ~30MB.

**Concurrency**: single-process middleware under the GIL; `OrderedDict` mutations are atomic at the bytecode level. No explicit locking required for v1. (If multi-worker FastAPI deployment is adopted later, each worker has its own map — per-worker per-IP budget. Documented limitation.)

**Visibility**: NEVER serialized to a non-operator surface. The audit row carries `source_ip_keyed` (FR-009) but never `current_tokens` or `last_refill_at` — those are internal limiter bookkeeping.

---

### `NetworkRateLimitRejectedRecord` (audit row shape)

The shape of an `admin_audit_log` row written by the rejection-coalescing flush task (research.md §6). One row per `(source_ip_keyed, minute_bucket)` rather than per-rejection (FR-009).

```python
@dataclass(frozen=True)
class NetworkRateLimitRejectedRecord:
    action: Literal["network_rate_limit_rejected"]
    source_ip_keyed: str           # the limiter's keying form (full IPv4 or /64 IPv6 prefix); NEVER raw v6 host
    minute_bucket: int             # floor(rejected_at_epoch / 60); identifies the coalescing window
    first_rejected_at: datetime    # earliest rejection in the window
    last_rejected_at: datetime     # latest rejection in the window
    rejection_count: int           # number of rejections coalesced into this row (always >= 1)
    endpoint_paths_seen: list[str] # distinct paths rejected within the window (capped to a small N to bound row size)
    methods_seen: list[str]        # distinct HTTP methods rejected within the window
    limiter_window_remaining_s: float | None  # informational: seconds until the limiter would admit the next request from this IP at the time of the latest rejection
```

**Persisted fields** in `admin_audit_log` (existing table columns):
- `action = "network_rate_limit_rejected"`
- `target_id = source_ip_keyed` (the entity being rate-limited)
- `previous_value` is unused (`null`) — the limiter has no "previous state" semantics for rejections.
- `new_value` is a JSON object carrying `(minute_bucket, first_rejected_at, last_rejected_at, rejection_count, endpoint_paths_seen, methods_seen, limiter_window_remaining_s)`.

**Coalescing rule** (per research.md §6): the in-memory accumulator `dict[(source_ip_keyed, minute_bucket), CoalesceState]` aggregates per-rejection events. The background flush task wakes every minute, drains complete-minute buckets, writes one row per bucket, and clears them.

**Privacy contract** (SC-009): the row MUST NOT include the rejected request's headers, query string, or body content. The `endpoint_paths_seen` field is path-only (no query string). Implementation MUST strip query strings before adding to the set.

---

### `ExemptPathRegistry` (frozen module-level constant)

The fixed set of `(method, path)` pairs that bypass the limiter middleware entirely (FR-006).

```python
EXEMPT_PATHS: tuple[tuple[str, str], ...] = (
    ("GET", "/health"),
    ("GET", "/metrics"),
)
```

**Read-only at runtime**: defined at module load in `src/middleware/network_rate_limit.py`. Not operator-configurable in v1 (clarify session 2026-05-08).

**Match semantics**:
- Exact path match (no prefix matching, no glob).
- Method-restricted: `POST /metrics` is NOT exempt; falls through to normal limiter handling.
- The check runs before any source-IP resolution work, so exempt requests incur no keying cost (V14).

**Future evolution**: a v2 amendment may introduce `SACP_NETWORK_RATELIMIT_EXEMPT_PATHS` to make the set operator-configurable. v1 is fixed.

---

### `SourceIPUnresolvableRecord` (audit row shape)

The shape of an `admin_audit_log` row written when source IP cannot be determined for a request (FR-012). NOT coalesced — these are rare and forensically important.

```python
@dataclass(frozen=True)
class SourceIPUnresolvableRecord:
    action: Literal["source_ip_unresolvable"]
    rejected_at: datetime
    request_path: str              # path-only; no query string
    request_method: str
    reason: str                    # one of: "no_peer", "malformed_forwarded_header", "no_xff_when_trust_enabled", "parse_error"
```

**Persisted fields** in `admin_audit_log`:
- `action = "source_ip_unresolvable"`
- `target_id = null` (no IP to attribute to — that's the entire condition)
- `previous_value = null`
- `new_value` is a JSON object carrying `(rejected_at, request_path, request_method, reason)`.

**Sequencing**: written before the HTTP 400 response is returned. Failure to write does NOT cause the request to fall through (the 400 still goes out); the audit-write failure is logged via the existing audit-failure path.

---

## Cross-spec references

- **Spec 002 (mcp-server)** — the MCP server on port 8750 is the v1 surface protected by this middleware. No schema change.
- **Spec 003 (turn-loop-engine) §FR-030** — `routing_log` per-stage timing capture; the limiter middleware's own duration surfaces through this channel on a sample of requests (V14 budget). No new `routing_log.reason` enum values introduced by this spec.
- **Spec 016 (prometheus-metrics) FR-002** — `/metrics` is in this spec's exempt set; FR-010 extends `sacp_rate_limit_rejection_total` with two labels (`endpoint_class`, `exempt_match`). Cross-ref [contracts/metrics.md](./contracts/metrics.md).
- **Spec 011 (web-ui)** — NO amendment for this spec. Network-layer limiting is operator-facing infrastructure (V13 parallel to spec 016); no SPA surface.
- **Existing §7.5 application-layer per-participant limiter** — no shared state, no shared code path. The two limiters are independently testable (FR-007).
- **Constitution §6.5 (Auth, Phase 1)** — bcrypt-hashing of static tokens; this spec's threat model anchor.
- **Constitution V9 (Log integrity)** — `admin_audit_log` is append-only; this spec adds two new `action` strings without schema change. Cross-ref [contracts/audit-events.md](./contracts/audit-events.md).
