"""Network-layer per-IP rate-limiting middleware (spec 019).

Token-bucket per source-IP keyed form (IPv4 /32, IPv6 /64). Runs as the
OUTERMOST middleware on every non-exempt inbound HTTP request to the MCP
server (port 8750) so unauthenticated flood traffic cannot turn bcrypt's
CPU work factor into a CPU-DoS vector. The middleware shares NO state
with the existing application-layer per-participant limiter (FR-007).

Phase-2 reuse note: the middleware is registered process-wide (not
per-port). Phase-2 wiring on port 8751 (Web UI) is a registration call
in the Web UI app factory ([src/web_ui/app.py](../web_ui/app.py)) -- not
a spec change. See specs/019-network-rate-limiting/spec.md "Assumptions".

Cross-refs:
- specs/019-network-rate-limiting/spec.md (FR-001 .. FR-015)
- specs/019-network-rate-limiting/data-model.md
- specs/019-network-rate-limiting/contracts/middleware-ordering.md
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# FR-006: fixed exempt set, GET-only. Exact path match. Defined at module
# load; read-only at runtime. Future amendment may make this operator-
# configurable via SACP_NETWORK_RATELIMIT_EXEMPT_PATHS (out of scope for v1).
EXEMPT_PATHS: tuple[tuple[str, str], ...] = (
    ("GET", "/health"),
    ("GET", "/metrics"),
)

# FR-005: fixed rejection body. Privacy contract -- MUST NOT echo any
# request content (path, query, headers, body). Stored as bytes so we
# don't allocate per rejection.
_REJECTION_BODY: bytes = b"rate limit exceeded"


@dataclass
class PerIPBudget:
    """Token-bucket state for one source-IP keyed form (data-model.md)."""

    source_ip_keyed: str
    current_tokens: float
    last_refill_at: float


def evaluate_bucket(
    budget: PerIPBudget,
    rpm: int,
    burst: int,
    now: float,
) -> tuple[bool, float]:
    """Lazy-refill + admit/reject decision for one bucket.

    Returns ``(admitted, post_decision_tokens)``. The caller uses the
    post-decision token count to derive ``Retry-After`` on rejection.
    research.md section1: lazy refill via timestamp delta, O(1) per request.
    """
    elapsed = max(0.0, now - budget.last_refill_at)
    refill = elapsed * rpm / 60.0
    budget.current_tokens = min(float(burst), budget.current_tokens + refill)
    budget.last_refill_at = now
    if budget.current_tokens >= 1.0:
        budget.current_tokens -= 1.0
        return True, budget.current_tokens
    return False, budget.current_tokens


def key_source_ip(remote_addr: str | None) -> str | None:
    """Transform a peer address to the keying form (FR-004).

    IPv4 -> full /32 dotted-decimal. IPv6 -> first 64 bits as canonical
    hex. Mapped IPv4 (``::ffff:1.2.3.4``) is unmapped to its IPv4 form.
    Returns None on parse failure (drives the FR-012 rejection branch).
    """
    if not remote_addr:
        return None
    candidate = remote_addr.split("%", 1)[0]  # strip zone id (e.g. fe80::%eth0)
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return str(addr.ipv4_mapped)
    if isinstance(addr, ipaddress.IPv4Address):
        return str(addr)
    return _ipv6_64_prefix(addr)


def _ipv6_64_prefix(addr: ipaddress.IPv6Address) -> str:
    """Return the first 64 bits of an IPv6 address as canonical hex."""
    packed = addr.packed[:8]
    int_prefix = int.from_bytes(packed, "big")
    # Format as :-separated 16-bit groups so the keyed form is human-readable.
    groups = [f"{(int_prefix >> (48 - 16 * i)) & 0xFFFF:x}" for i in range(4)]
    return ":".join(groups) + "::/64"


def parse_forwarded_header(headers: dict[str, str]) -> str | None:
    """Parse the rightmost source IP from ``Forwarded`` or ``X-Forwarded-For``.

    Gated by SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=true. RFC 7239
    ``Forwarded`` is preferred when present and parseable; XFF rightmost is
    the fallback. Returns None when neither header yields a usable address.
    research.md section4: rightmost-trusted-entry rule (one trust hop, the
    operator's own proxy).
    """
    forwarded = headers.get("forwarded") or headers.get("Forwarded")
    if forwarded:
        ip = _parse_rfc7239_forwarded(forwarded)
        if ip:
            return ip
    xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
    if xff:
        return _parse_xff_rightmost(xff)
    return None


def _parse_rfc7239_forwarded(value: str) -> str | None:
    """Extract the rightmost ``for=`` parameter from an RFC 7239 chain."""
    entries = [e.strip() for e in value.split(",") if e.strip()]
    for entry in reversed(entries):
        for param in entry.split(";"):
            key, _, val = param.strip().partition("=")
            if key.lower() == "for":
                return _strip_forwarded_for(val)
    return None


def _strip_forwarded_for(raw: str) -> str | None:
    """Strip quotes / brackets / port from an RFC 7239 ``for`` value."""
    val = raw.strip().strip('"')
    if not val or val.lower() in ("unknown", "_hidden"):
        return None
    if val.startswith("[") and "]" in val:
        return val[1 : val.index("]")]
    # IPv4 may carry :port; IPv6 without brackets has no port form here.
    if val.count(":") == 1:
        return val.split(":", 1)[0]
    return val


def _parse_xff_rightmost(value: str) -> str | None:
    """Rightmost non-empty entry of an X-Forwarded-For chain."""
    entries = [e.strip() for e in value.split(",") if e.strip()]
    return entries[-1] if entries else None


@dataclass(frozen=True)
class LimiterConfig:
    """Resolved limiter knobs (one instance per app, set at registration)."""

    rpm: int
    burst: int
    max_keys: int
    trust_forwarded_headers: bool


class _LRUBucketMap:
    """OrderedDict-backed LRU map of PerIPBudget entries (research.md section3)."""

    def __init__(self, max_keys: int) -> None:
        self._max_keys = max_keys
        self._map: OrderedDict[str, PerIPBudget] = OrderedDict()

    def __len__(self) -> int:
        return len(self._map)

    def get_or_create(self, key: str, burst: int, now: float) -> PerIPBudget:
        """Fetch or create a bucket; move-to-end on access; LRU-evict if over."""
        existing = self._map.get(key)
        if existing is not None:
            self._map.move_to_end(key)
            return existing
        budget = PerIPBudget(
            source_ip_keyed=key,
            current_tokens=float(burst),
            last_refill_at=now,
        )
        self._map[key] = budget
        if len(self._map) > self._max_keys:
            self._map.popitem(last=False)  # O(1) amortized
        return budget


def _resolve_source_ip(
    scope: dict[str, Any],
    config: LimiterConfig,
) -> tuple[str | None, str]:
    """Return (source_ip_keyed, unresolvable_reason).

    On success, ``source_ip_keyed`` is the FR-004 keying form and the
    second tuple slot is unused (empty string). On failure, the first
    slot is None and the second names the failure mode for the audit
    row (FR-012).
    """
    headers = _scope_headers(scope)
    if config.trust_forwarded_headers:
        return _resolve_forwarded(headers)
    client = scope.get("client")
    if not client:
        return None, "no_peer"
    raw = client[0] if isinstance(client, tuple | list) else None
    keyed = key_source_ip(raw)
    return (keyed, "") if keyed else (None, "parse_error")


def _resolve_forwarded(headers: dict[str, str]) -> tuple[str | None, str]:
    """Resolution branch when SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS=true."""
    forwarded_ip = parse_forwarded_header(headers)
    if forwarded_ip is None:
        if "forwarded" in headers or "x-forwarded-for" in headers:
            return None, "malformed_forwarded_header"
        return None, "no_xff_when_trust_enabled"
    keyed = key_source_ip(forwarded_ip)
    return (keyed, "") if keyed else (None, "parse_error")


def _scope_headers(scope: dict[str, Any]) -> dict[str, str]:
    """Normalize ASGI ``scope['headers']`` to a lower-cased str dict."""
    out: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []) or []:
        name = _decode_header(raw_name).lower()
        value = _decode_header(raw_value)
        out[name] = value
    return out


def _decode_header(value: bytes | str) -> str:
    """Decode a single ASGI header value (bytes -> latin-1 str; str as-is)."""
    return value.decode("latin-1") if isinstance(value, bytes) else str(value)


class NetworkRateLimitMiddleware:
    """ASGI middleware: per-IP token-bucket rate limiter (spec 019)."""

    def __init__(
        self,
        app: Any,
        *,
        rpm: int,
        burst: int,
        max_keys: int,
        trust_forwarded_headers: bool,
    ) -> None:
        self.app = app
        self.config = LimiterConfig(
            rpm=rpm,
            burst=burst,
            max_keys=max_keys,
            trust_forwarded_headers=trust_forwarded_headers,
        )
        self._buckets = _LRUBucketMap(max_keys=max_keys)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Dispatch by ASGI scope type; non-http/websocket pass through.

        V14 budget (spec 003 sectionFR-030): the limiter's own per-request work
        (resolution + token-bucket arithmetic) is captured under the stage
        name ``network_rate_limit_ms`` via ``record_stage``. The downstream
        ``await self.app(...)`` is intentionally OUTSIDE the timing window
        -- we measure the limiter's overhead, not the request lifecycle.
        """
        scope_type = scope.get("type")
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path, method = _scope_path_method(scope, scope_type)
        if (method, path) in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        admit_start = time.monotonic()
        keyed, reason, decision = self._decide(scope)
        _record_stage_timing("network_rate_limit_ms", admit_start)
        await self._dispatch(
            scope,
            receive,
            send,
            keyed=keyed,
            reason=reason,
            decision=decision,
            path=path,
            method=method,
            scope_type=scope_type,
        )

    async def _dispatch(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        *,
        keyed: str | None,
        reason: str,
        decision: tuple[bool, int],
        path: str,
        method: str,
        scope_type: str,
    ) -> None:
        """Route to admit / reject-429 / reject-400 based on the decision tuple."""
        if keyed is None:
            await _send_unresolvable_400(send, scope_type=scope_type)
            _emit_unresolvable_audit(path=path, method=method, reason=reason)
            _increment_rejection_metric()
            return
        admitted, retry_after = decision
        if admitted:
            await self.app(scope, receive, send)
            return
        await _send_429(send, retry_after=retry_after, scope_type=scope_type)
        _emit_rejection_audit(
            source_ip_keyed=keyed,
            path=path,
            method=method,
            remaining_s=float(retry_after),
        )
        _increment_rejection_metric()

    def _decide(
        self,
        scope: dict[str, Any],
    ) -> tuple[str | None, str, tuple[bool, int]]:
        """Resolve source IP + run token-bucket.

        Returns ``(keyed, reason, (admitted, retry_after))``.
        """
        keyed, reason = _resolve_source_ip(scope, self.config)
        if keyed is None:
            return None, reason, (False, 0)
        now = time.monotonic()
        budget = self._buckets.get_or_create(keyed, self.config.burst, now)
        admitted, remaining = evaluate_bucket(budget, self.config.rpm, self.config.burst, now)
        retry_after = 0 if admitted else _retry_after_seconds(remaining, self.config.rpm)
        return keyed, "", (admitted, retry_after)


def _scope_path_method(scope: dict[str, Any], scope_type: str) -> tuple[str, str]:
    """Extract path + uppercase method from an ASGI scope (WS upgrades default GET)."""
    path = scope.get("path", "")
    method = (scope.get("method") or ("GET" if scope_type == "websocket" else "")).upper()
    return path, method


def _record_stage_timing(stage_name: str, start: float) -> None:
    """Record per-stage duration if a turn-context is active (V14 / FR-030)."""
    try:
        from src.orchestrator.timing import record_stage

        duration_ms = int((time.monotonic() - start) * 1000)
        record_stage(stage_name, duration_ms)
    except Exception:  # pragma: no cover - instrumentation must never fail-open
        logger.debug("network_rate_limit timing capture failed", exc_info=True)


def _retry_after_seconds(post_decision_tokens: float, rpm: int) -> int:
    """Seconds until the bucket admits the next request (RFC 6585 integer form)."""
    if rpm <= 0:
        return 1
    needed = max(0.0, 1.0 - post_decision_tokens)
    seconds = needed * 60.0 / rpm
    return max(1, int(seconds + 0.999))


async def _send_429(send: Any, *, retry_after: int, scope_type: str) -> None:
    """Emit HTTP 429 with Retry-After + fixed body (FR-005)."""
    if scope_type == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(_REJECTION_BODY)).encode("ascii")),
                (b"retry-after", str(retry_after).encode("ascii")),
            ],
        },
    )
    await send({"type": "http.response.body", "body": _REJECTION_BODY, "more_body": False})


async def _send_unresolvable_400(send: Any, *, scope_type: str) -> None:
    """Emit HTTP 400 for source-IP-unresolvable requests (FR-012)."""
    body = b"source ip unresolvable"
    if scope_type == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    await send(
        {
            "type": "http.response.start",
            "status": 400,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        },
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def _emit_rejection_audit(
    *,
    source_ip_keyed: str,
    path: str,
    method: str,
    remaining_s: float,
) -> None:
    """Record a coalesced rejection. Late-imported to keep this module light."""
    from src.audit.network_rate_limit_audit import record_rejection

    # Strip query string before recording (privacy contract SC-009).
    path_only = path.split("?", 1)[0] if path else path
    record_rejection(
        source_ip_keyed=source_ip_keyed,
        path=path_only,
        method=method,
        remaining_s=float(remaining_s),
        now=time.time(),
    )


def _emit_unresolvable_audit(*, path: str, method: str, reason: str) -> None:
    """Emit a NON-coalesced source_ip_unresolvable audit row (FR-012)."""
    from src.audit.network_rate_limit_audit import emit_source_ip_unresolvable

    path_only = path.split("?", 1)[0] if path else path
    emit_source_ip_unresolvable(
        path=path_only,
        method=method,
        reason=reason or "parse_error",
        now=time.time(),
    )


def _increment_rejection_metric() -> None:
    """Increment spec 016's counter with this spec's labels (FR-010)."""
    from src.observability.metrics import increment_network_rate_limit_rejection

    increment_network_rate_limit_rejection()


__all__ = [
    "EXEMPT_PATHS",
    "LimiterConfig",
    "NetworkRateLimitMiddleware",
    "PerIPBudget",
    "evaluate_bucket",
    "key_source_ip",
    "parse_forwarded_header",
]
