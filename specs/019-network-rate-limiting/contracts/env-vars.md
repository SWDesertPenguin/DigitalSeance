# Contract: New Environment Variables (V16)

**Branch**: `019-network-rate-limiting` | **Source**: spec FR-013, Configuration (V16) section | **Date**: 2026-05-08

Five new `SACP_NETWORK_RATELIMIT_*` environment variables. Per Constitution V16, each MUST have a validator function in `src/config/validators.py` (registered in the `VALIDATORS` tuple) AND a corresponding section in `docs/env-vars.md` with the six standard fields BEFORE `/speckit.tasks` runs (FR-013 — V16 deliverable gate).

The six standard fields per `docs/env-vars.md` convention: Default, Type, Valid range, Blast radius, Validation rule, Source spec.

---

## `SACP_NETWORK_RATELIMIT_ENABLED`

| Field | Value |
|---|---|
| **Default** | `false` |
| **Type** | boolean (string `"true"`/`"false"`, case-insensitive) |
| **Valid range** | exactly `true` or `false` (after case-folding) |
| **Blast radius on invalid** | V16 startup validator refuses to bind ports |
| **Validation rule** | `validators.validate_network_ratelimit_enabled` |
| **Source spec(s)** | spec 019 FR-001, FR-014, Configuration (V16) section |

**Note**: Master switch. When `false` (the default), the middleware is NOT registered and pre-feature behavior is preserved byte-identically (SC-006). When `true`, the middleware is registered FIRST per FR-001 and FR-002.

---

## `SACP_NETWORK_RATELIMIT_RPM`

| Field | Value |
|---|---|
| **Default** | `60` |
| **Type** | positive integer, requests per minute |
| **Valid range** | `[1, 6000]` |
| **Blast radius on invalid** | V16 startup validator refuses to bind ports |
| **Validation rule** | `validators.validate_network_ratelimit_rpm` |
| **Source spec(s)** | spec 019 FR-003, Configuration (V16) section |

**Note**: Steady-state requests-per-minute admitted per source IP. The default of 60 is one request per second on average per IP — generous for human-driven MCP clients. Operator tunes upward for NAT-fronted traffic. When `_ENABLED=true` and `_RPM` is unset, the validator uses the default 60 (no startup exit).

---

## `SACP_NETWORK_RATELIMIT_BURST`

| Field | Value |
|---|---|
| **Default** | `15` (= `RPM / 4` rounded; allows ~15-second bursts at the steady-state rate) |
| **Type** | positive integer, tokens |
| **Valid range** | `[1, 10000]` |
| **Blast radius on invalid** | V16 startup validator refuses to bind ports |
| **Validation rule** | `validators.validate_network_ratelimit_burst` |
| **Source spec(s)** | spec 019 FR-003, Configuration (V16) section |

**Note**: Token-bucket capacity. Allows short bursts above the steady-state RPM. The default of 15 (= 60/4) means a quiet-then-active client can spike up to 15 requests in a quarter-minute before the steady-state rate kicks in. Operators raising RPM should typically raise BURST proportionally.

---

## `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS`

| Field | Value |
|---|---|
| **Default** | `false` |
| **Type** | boolean (string `"true"`/`"false"`, case-insensitive) |
| **Valid range** | exactly `true` or `false` (after case-folding) |
| **Blast radius on invalid** | V16 startup validator refuses to bind ports |
| **Validation rule** | `validators.validate_network_ratelimit_trust_forwarded_headers` |
| **Source spec(s)** | spec 019 FR-011, Configuration (V16) section |

**Note**: Trust-by-opt-in for forwarded-header parsing. When `false` (the default), the middleware uses the immediate peer IP and ignores `Forwarded` (RFC 7239) and `X-Forwarded-For` headers. When `true`, the middleware parses the rightmost-trusted entry of `Forwarded` (preferred) or `X-Forwarded-For` (fallback) per research.md §4. The operator is responsible for ensuring the upstream proxy sanitizes inbound headers before forwarding.

---

## `SACP_NETWORK_RATELIMIT_MAX_KEYS`

| Field | Value |
|---|---|
| **Default** | `100000` |
| **Type** | positive integer, count of distinct keyed-IP entries held in memory |
| **Valid range** | `[1024, 1000000]` |
| **Blast radius on invalid** | V16 startup validator refuses to bind ports |
| **Validation rule** | `validators.validate_network_ratelimit_max_keys` |
| **Source spec(s)** | spec 019 FR-004 (memory bound), Configuration (V16) section |

**Note**: LRU bound on the per-IP budget map. When the map exceeds this size, the least-recently-accessed entry is evicted (research.md §3). Memory bound is `MAX_KEYS × ~300 bytes per entry`; default 100k = ~30MB worst case. Raise toward 1M for deployments with high IP diversity (public-internet-exposed, or NAT-egress-fronted with many client IPs).

---

## Validator implementation pattern

All five validators follow the existing `src/config/validators.py` pattern (returning `ValidationFailure | None`, registered in the module-level `VALIDATORS` tuple). Sketch:

```python
def validate_network_ratelimit_enabled() -> ValidationFailure | None:
    val = os.environ.get("SACP_NETWORK_RATELIMIT_ENABLED", "false").lower()
    if val not in ("true", "false"):
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_ENABLED",
            f"must be 'true' or 'false'; got {val!r}",
        )
    return None


def validate_network_ratelimit_rpm() -> ValidationFailure | None:
    raw = os.environ.get("SACP_NETWORK_RATELIMIT_RPM", "60")
    try:
        val = int(raw)
    except ValueError:
        return ValidationFailure("SACP_NETWORK_RATELIMIT_RPM", f"not an integer: {raw!r}")
    if not (1 <= val <= 6000):
        return ValidationFailure(
            "SACP_NETWORK_RATELIMIT_RPM",
            f"out of range [1, 6000]; got {val}",
        )
    return None
```

Each validator is appended to the `VALIDATORS` tuple. Startup walks the tuple via `validate_all()` and raises `ConfigValidationError` before any port is bound.

---

## docs/env-vars.md sections

Same five vars get sections in `docs/env-vars.md` with the same six fields (rendered per existing convention in that file). The validator and the doc section MUST land together in the same task per FR-013; CI's V16 gate (`scripts/check_env_vars.py` per spec 012 FR-005) flags any var with a validator but no doc section, and vice versa.

---

## Test obligations

- `test_019_validators.py` covers each of the five validators:
  - Valid value passes (returns `None`).
  - Out-of-range value returns a `ValidationFailure` with the offending var name.
  - Unparseable value (e.g. `_RPM='abc'`) returns a `ValidationFailure`.
  - Unset value uses the documented default and passes.
- `test_019_validators.py` covers the V16 startup gate: invalid value at startup MUST exit before binding (raises `ConfigValidationError`).
- No cross-validator dependencies among the five vars — each is independently validated. (Contrast with spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` cross-validator pair; this spec has no equivalent coupling.)
