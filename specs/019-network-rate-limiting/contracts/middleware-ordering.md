# Contract: FastAPI middleware-registration ordering

**Branch**: `019-network-rate-limiting` | **Source**: spec FR-001, FR-002 | **Date**: 2026-05-08

The network-layer rate-limiting middleware MUST be the FIRST middleware on every inbound non-exempt HTTP request to the MCP server (port 8750). "First" means: the limiter is the outermost middleware on the request stack; it sees every request before any other middleware (auth, bcrypt validation, logging, CORS, anything) gets the opportunity to run.

This document specifies (1) the FastAPI registration semantics that achieve "first," (2) the startup-test signature that proves it, and (3) the failure modes the test must catch.

---

## FastAPI registration semantics

FastAPI middleware is registered via `app.add_middleware(...)` calls inside `src/mcp_server/app.py::_add_middleware`, which is invoked from `create_app()`. FastAPI processes middleware in **reverse order of registration**: the LAST `add_middleware` call becomes the OUTERMOST middleware (the one that wraps everything else and sees requests first).

To make `NetworkRateLimitMiddleware` the outermost / first-to-run, it MUST be the LAST `add_middleware` call in `_add_middleware`'s registration block.

### Required pattern

```python
# src/mcp_server/app.py — inside _add_middleware(app)

# Register inner middleware first (executes later in request handling)
app.add_middleware(SomeInnerMiddleware, ...)
app.add_middleware(AuthMiddleware, ...)
app.add_middleware(LoggingMiddleware, ...)

# Network rate-limit middleware MUST be registered LAST so it becomes
# the OUTERMOST middleware. This is the FR-001 / FR-002 contract:
# every non-exempt request hits the limiter BEFORE auth or bcrypt.
if settings.network_ratelimit_enabled:
    app.add_middleware(NetworkRateLimitMiddleware, ...)
```

### Conditional registration

When `SACP_NETWORK_RATELIMIT_ENABLED=false` (the default), the middleware MUST NOT be registered at all (FR-014, SC-006). The `if` guard above is load-bearing: an unconditionally-registered no-op middleware is NOT pre-feature-byte-identical because it still affects the middleware order and adds a frame to the request stack.

---

## Startup-test signature

A test in `tests/test_019_middleware_order.py` MUST run at startup-equivalent fixture time (the FastAPI test client's `app.user_middleware` introspection) and assert two properties:

### Property 1 — When ENABLED, NetworkRateLimit is outermost

```python
def test_network_ratelimit_is_outermost_when_enabled(monkeypatch):
    """FR-002: NetworkRateLimit MUST be the outermost middleware when ENABLED=true."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_RPM", "60")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_BURST", "15")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS", "false")
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_MAX_KEYS", "100000")

    app = create_app()  # the project's app factory

    # FastAPI's add_middleware() prepends to user_middleware (insert at
    # index 0), so the LAST registered middleware ends up at index 0 —
    # which becomes the OUTERMOST. The FIRST entry of the list is the
    # outermost; the LAST entry is the innermost.
    middleware_classes = [m.cls for m in app.user_middleware]
    assert middleware_classes, "expected at least one middleware registered"
    assert middleware_classes[0].__name__ == "NetworkRateLimitMiddleware", (
        f"FR-002 violated: NetworkRateLimitMiddleware MUST be outermost "
        f"(index 0 of user_middleware after FastAPI's prepend semantics); "
        f"got order {[c.__name__ for c in middleware_classes]}"
    )
```

### Property 2 — When DISABLED, NetworkRateLimit is absent

```python
def test_network_ratelimit_absent_when_disabled(monkeypatch):
    """FR-014, SC-006: middleware MUST NOT be registered when ENABLED=false."""
    monkeypatch.setenv("SACP_NETWORK_RATELIMIT_ENABLED", "false")

    app = create_app()

    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "NetworkRateLimitMiddleware" not in middleware_classes, (
        f"SC-006 violated: middleware registered when ENABLED=false; "
        f"got order {middleware_classes}"
    )
```

These two tests together prove the contract: registration is conditional on the master switch, and when the switch is on the middleware is positioned correctly.

---

## Failure modes the test must catch

The test MUST fail (in CI, blocking merge) for any of these regressions:

1. **Auth middleware registered after limiter** — would wrap the limiter, putting auth on the outside; bcrypt would run before the limiter check. Catches a developer pattern of "I added a new auth middleware, registered it last because the convention was 'last is outermost' but I forgot the limiter contract."
2. **Limiter registered first instead of last** — places the limiter innermost, where it would only see requests that already passed through auth. Catches a misreading of FastAPI's reverse-order semantics.
3. **Limiter unconditionally registered** — even with `_ENABLED=false`, the middleware appears in `user_middleware`. Breaks SC-006 byte-identical pre-feature behavior.
4. **Limiter conditionally registered AND another middleware also registered conditionally on a different env var, in a way that lets the limiter slip from outermost** — e.g., a debug-only middleware registered after the limiter when a debug env var is set. Catches subtle ordering drift across feature flags. The test pins the limiter as outermost regardless of other conditional middleware.

The test does NOT need to verify behavioral correctness of the limiter (that is `test_019_flood_blocked.py`'s job). It verifies registration-order topology only.

---

## Operator-visible introspection

For human operators verifying the contract in production (per [quickstart.md §"Verify middleware registration order"](../quickstart.md)), the orchestrator emits a startup log line listing the middleware order outermost-first:

```text
INFO  Middleware order (outermost first): NetworkRateLimit, Auth, Logging, ...
```

This log line is emitted exactly once per startup, after the `add_middleware` block completes and before port binding. Implementation: walk `app.user_middleware` in reverse and join class names. The log line is informational; the FR-002 contract is enforced by the CI test, not by parsing log output.

---

## Cross-spec references

- **Constitution §6.5** — bcrypt-hashing of static tokens. The middleware-ordering contract exists to ensure bcrypt does not run on rate-limited requests; this is the threat-model anchor.
- **Spec 002 (mcp-server)** — defines the auth middleware that this spec's middleware MUST run before.
- **Spec 016 (prometheus-metrics) FR-002** — `/metrics` is in this spec's exempt set; the exempt-path check runs INSIDE the limiter middleware (i.e., the limiter is still outermost; it just early-returns for exempt paths without consuming budget).
