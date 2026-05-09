# Research: Network-Layer Per-IP Rate Limiting

**Branch**: `019-network-rate-limiting` | **Date**: 2026-05-08 | **Plan**: [plan.md](./plan.md)

Resolves the eight open decisions queued in [plan.md §"Phase 0 — Outline & Research"](./plan.md). Each section answers one question; each section closes with a Decision / Rationale / Alternatives format.

---

## §1 — Token-bucket implementation in FastAPI middleware

**Decision**: lazy refill per-request via timestamp delta. The middleware computes the refill amount each time a request arrives for a given keyed-IP using `(now - last_refill_at) × rpm / 60.0`, clamps the bucket to `BURST` capacity, decrements one token, and stores `last_refill_at = now`. No background timer driving refill.

**Rationale**: lazy refill gives O(1) per-request work, matches the V14 budget for this stage, and avoids any per-key timer state. The token bucket only needs to know the elapsed time since the last access — refill happens at access time, not at fixed intervals. This also means evicted-then-restored keys behave correctly (a long-quiet IP returning later is granted a full bucket without any per-key bookkeeping). Asyncio-safe by being purely synchronous arithmetic guarded by a single per-key spinlock-equivalent (atomic `OrderedDict` operations under the GIL).

**Alternatives considered**:
- **Background timer driving refill** — sounds simpler ("every second, add `RPM/60` tokens to every bucket") but is O(N) per tick where N is the live keyed-IP count, which under flood approaches `MAX_KEYS`. Rejected as a worst-case CPU-DoS surface in its own right.
- **Leaky-bucket variant** — equivalent semantics for steady-state but worse for burst handling. The spec explicitly chose token-bucket for burst smoothing.
- **Sliding-window log** — keeps per-request timestamps and counts within a window. O(window-size) per request and unbounded memory under flood. Rejected.

---

## §2 — Lazy refill vs. background timer

**Decision**: lazy refill is the default and only implementation. (Confirms §1.)

**Rationale**: documented separately because the "background timer" alternative is a common first-instinct implementation that reviewers might propose. The rejection rationale is load-bearing: a per-tick O(N) refill scales with the very thing the limiter is trying to defend against (flood-induced key proliferation), turning the limiter into its own DoS amplifier. Lazy refill scales with request rate — exactly the rate the operator is sizing the limiter for.

**Alternatives considered**: see §1.

---

## §3 — LRU eviction at MAX_KEYS bound

**Decision**: `collections.OrderedDict` with `move_to_end` on access and `popitem(last=False)` on overflow. Bound is `SACP_NETWORK_RATELIMIT_MAX_KEYS` (default 100_000, range `[1024, 1_000_000]`).

**Rationale**: stdlib-only, O(1) amortized for both the access-update (move-to-end) and the eviction (popitem from front). Memory bound under flood is `MAX_KEYS × sizeof(PerIPBudget)` ≈ a few hundred bytes per entry, so 100k keys = ~30MB worst case. The default is conservative for a single MCP server; operators with larger IP-diversity surfaces (NAT egress fronts, public deployments) can raise to 1M without code change.

**Alternatives considered**:
- **`functools.lru_cache`** — designed for memoization, not for stateful per-key data with mutation. Rejected as a misuse of the API.
- **Third-party LRU library (`cachetools`, `lru-dict`)** — adds a dependency for a stdlib-feasible feature. V11 supply-chain surface for no behavioral upside. Rejected.
- **Unbounded map with periodic prune** — easy to write but defers the problem; under sustained flood the map grows until prune fires, with no guarantee of timely reclamation. Rejected.
- **Time-windowed eviction (drop entries older than N minutes)** — works but is O(N) per scan and conflates eviction policy with refill semantics. Rejected.

---

## §4 — RFC 7239 `Forwarded` vs. `X-Forwarded-For` parsing precedence

**Decision**: prefer `Forwarded` (RFC 7239) when present and parseable; fall back to `X-Forwarded-For` (de-facto standard). When `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=false` (the default), neither header is consulted — the immediate peer IP is the source. When `true`, parse the rightmost-trusted entry per RFC 7239's spec.

**Rationale**: `Forwarded` is the RFC-blessed format and is structured (`for=` parameter, optional `host=`/`proto=`/`by=`). `X-Forwarded-For` is the de-facto compatibility format; many real-world proxies still emit only `X-Forwarded-For`. Preferring the RFC format when present matches the principle "use the more specific signal when available." Rightmost-trusted-entry rule means: when a chain like `for=1.2.3.4, for=5.6.7.8, for=9.10.11.12` arrives, the operator's responsibility is to trust the rightmost N hops they control; v1 picks just the rightmost (one trust hop, the operator's own proxy).

**Alternatives considered**:
- **`X-Forwarded-For` only** — ignores RFC 7239. Rejected.
- **Leftmost-entry parsing** — common but wrong for trust-by-opt-in: the leftmost entry is the original client (untrusted), the rightmost is the closest trusted hop. Rejected.
- **Configurable trust-hop count** — operator picks how many rightmost hops are trusted. Useful but adds an env var for v1. Drafted as a future amendment (likely v2 if multi-hop topologies emerge); v1 is single-hop.

---

## §5 — /64 IPv6 keying transform implementation

**Decision**: `ipaddress.IPv6Address(addr).packed[:8]` to extract the first 8 bytes (the /64 network prefix), then re-format as a stable string key (`hex(prefix_int).rstrip('L')` or equivalent). For IPv4: full 32-bit address as the key (`str(ipaddress.IPv4Address(addr))`).

**Rationale**: stdlib `ipaddress` module handles edge cases (link-local addresses, IPv4-mapped-IPv6 `::ffff:1.2.3.4`, IPv6 with zone identifiers like `%eth0`). Mapped IPv4 addresses are unmapped to IPv4 form before keying so an IPv4 client doesn't get a separate /64 v6 budget when they happen to arrive over a v6 socket. Link-local source addresses (`fe80::/10`) almost never appear at an internet-exposed surface; if they do, they're keyed as their /64 like any other v6 address. Performance: `ipaddress` parsing is ~microseconds per request — well below V14 budget.

**Alternatives considered**:
- **Manual byte-slicing without `ipaddress`** — saves a microsecond per request but loses edge-case correctness. Rejected.
- **Key on full /128 v6 address** — explicitly rejected by FR-004 because IPv6 hosts often use dynamic privacy addresses within their /64.
- **Configurable v6 prefix length (`/56`, `/48`, `/64`)** — useful for institutional networks but defers to v2.

---

## §6 — Audit-log per-(IP, minute) coalescing flush mechanism

**Decision**: in-memory accumulator `dict[(source_ip_keyed, minute_bucket), int]` where `minute_bucket = floor(now_ts / 60)`. A background asyncio task wakes every minute, drains the accumulator, writes one `admin_audit_log` row per `(source_ip_keyed, minute_bucket)` with `rejection_count = N`, and clears the accumulator. The flush is NOT in the request path — request-path code only increments the in-memory counter and increments the metric counter.

**Rationale**: keeps the V14 budget for the request path tight (one increment, no DB write). Bounds audit-log volume during sustained flooding to one row per (unique flooding IP, minute) — SC-008 requires this. The 1-minute granularity is a forensic-vs-volume trade-off documented in spec assumptions; operators investigating an active flood rely on the metrics surface for per-rejection counts. Crash durability: if the orchestrator crashes mid-minute, up to 60 seconds of coalesced rejections are lost — acceptable because the metrics counter (incremented per-rejection) survives via Prometheus scrape, providing the durable per-rejection record.

**Alternatives considered**:
- **Flush-on-rejection-batch (every N rejections)** — couples flush cadence to flood rate; under steady high-rate flood this becomes per-request, defeating the purpose. Rejected.
- **Synchronous write per-rejection** — abandons coalescing entirely. Rejected (FR-009 mandates coalescing).
- **External coalescing process** — ships rejections over a queue to a separate worker. Adds a dependency and a queue surface. Rejected.

---

## §7 — Spec 016 metric label set for `sacp_rate_limit_rejection_total`

**Decision**: extend the existing counter with two labels: `endpoint_class` (string, value `"network_per_ip"` for this spec's rejections, leaving room for `"app_layer_per_participant"` to be added by §7.5's existing limiter if it adopts the same counter), and `exempt_match` (boolean string `"true"`/`"false"` — always `"false"` for this spec's emissions because exempt paths bypass the limiter entirely). NO labels for source IP, query string, headers, or body content (FR-010, SC-009).

**Rationale**: cardinality-bounded — `endpoint_class` is a fixed enum (Phase 1 ships one value), `exempt_match` is two values. Joinable with existing spec 016 dashboards via the standard counter scrape path. The privacy contract test asserts the label set; CI catches any future addition that would inflate cardinality or leak PII.

**Alternatives considered**:
- **Per-source-IP label** — explodes cardinality under flood (one new time series per attacker IP). Rejected.
- **Per-path label** — leaks endpoint surface info to Prometheus consumers; many exporters fan out to less-trusted dashboards. Rejected (audit log carries the path; metric does not).
- **Single counter with no labels** — simpler but loses the `network_per_ip` vs `app_layer_per_participant` distinction once §7.5 adopts the counter. Rejected as a forward-compatibility loss.

---

## §8 — Topology-7 forward note

**Decision**: document that in topology 7 (MCP-to-MCP, Phase 3+ — orchestrator shrunk to state-management role with materially fewer or no participant-facing inbound HTTP surfaces) the middleware remains registered but typically idle. If the orchestrator still exposes `/health` or `/metrics`, those paths are exempt and unaffected by topology. If the orchestrator exposes no participant-facing inbound HTTP surfaces, the middleware sees zero traffic.

**Rationale**: forward-compatibility without spec amendment. The middleware is registered process-wide at startup; topology selection is a deployment-shape concern that does not require the middleware to be conditionally registered. Operators running topology 7 see no behavior change because there's no traffic to limit. The audit and metrics surfaces remain wired but emit nothing.

**Alternatives considered**:
- **Conditionally skip middleware registration in topology 7** — adds a topology-aware branch in `src/mcp_server/app.py::_add_middleware`. Unnecessary; idle middleware costs nothing. Rejected.
- **Ship spec 019 v2 when topology 7 lands** — premature; v1 is forward-compatible by construction.

---

## Summary of Resolutions

| # | Question | Decision |
|---|---|---|
| 1 | Token-bucket implementation | Lazy refill via timestamp delta, O(1) per request |
| 2 | Lazy vs. background timer | Lazy (background timer rejected as O(N) per tick) |
| 3 | LRU eviction at MAX_KEYS | `OrderedDict` move-to-end + `popitem(last=False)` |
| 4 | `Forwarded` vs `X-Forwarded-For` | RFC 7239 preferred; XFF fallback; rightmost-trusted entry |
| 5 | /64 IPv6 keying | `ipaddress.IPv6Address(addr).packed[:8]`; v4 keys at /32 |
| 6 | Audit coalescing flush | Background asyncio task, 1-minute cadence; NOT in request path |
| 7 | Metric label set | `(endpoint_class, exempt_match)` only; no PII / IP / path |
| 8 | Topology-7 forward note | Middleware registered but idle; no spec amendment needed |

All Phase 0 unknowns resolved. Phase 1 design docs (data-model.md, contracts/, quickstart.md) can proceed.
