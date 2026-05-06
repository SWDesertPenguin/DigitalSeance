# SACP Environment Variable Catalog

Authoritative reference for every `SACP_*` environment variable consumed
by the SACP orchestrator and Web UI. Per Constitution §12 V16, every var
has a documented type, valid range, and fail-closed behavior on invalid
values; the application validates every var at startup BEFORE binding
any port and exits with a clear error rather than silently accepting an
out-of-range default.

## Conventions

- Every var is prefixed `SACP_`.
- "Default" is the value used when the var is unset; `<required>` indicates
  no default (process exits non-zero if not set).
- "Validation rule" mirrors the per-var function in `src/config/validators.py`.
- "Blast radius on invalid" describes what fails when the value is wrong.
- Validation timing: `validate_all()` runs in `src/run_apps.py:main()` before
  `asyncio.run(_run())`, so an invalid value causes the process to exit
  before binding any port.
- Smoke check: `python -m src.run_apps --validate-config-only` runs validation
  only and exits 0/1.

## Validated vars

### `SACP_DATABASE_URL`

- **Default**: `<required>`
- **Type**: PostgreSQL URL (`postgresql://...` or `postgres://...`)
- **Valid range**: scheme must be `postgresql` or `postgres`; netloc (host[:port]) must be non-empty
- **Blast radius on invalid**: orchestrator cannot connect to Postgres; no functionality
- **Validation rule**: `validators.validate_database_url`
- **Source spec(s)**: 001 §FR-020 (encryption-at-rest scope), 003 §FR-019 (advisory-lock provider)

### `SACP_ENCRYPTION_KEY`

- **Default**: `<required>`
- **Type**: Fernet key (44-char URL-safe base64)
- **Valid range**: `len() == 44` AND `cryptography.fernet.Fernet(value)` accepts it without raising
- **Blast radius on invalid**: encryption-at-rest unavailable; participant `api_key_encrypted` columns inaccessible
- **Validation rule**: `validators.validate_encryption_key`
- **Source spec(s)**: 001 §FR-020, §FR-021

### `SACP_AUTH_LOOKUP_KEY`

- **Default**: `<required>`
- **Type**: high-entropy random string (>= 32 chars)
- **Valid range**: `len() >= 32` AND not equal to any documented placeholder
- **Blast radius on invalid**: orchestrator refuses to bind ports; auth path cannot compute the HMAC token-lookup index
- **Validation rule**: `validators.validate_auth_lookup_key`
- **Source spec(s)**: 002 audit C-02 (HMAC-keyed token lookup)
- **Note**: Distinct from `SACP_ENCRYPTION_KEY`. Used as the HMAC key for `participants.auth_token_lookup`. Rotate by re-issuing every active token (force re-login).

### `SACP_WEB_UI_COOKIE_KEY`

- **Default**: `<required>`
- **Type**: high-entropy random string (>= 32 chars)
- **Valid range**: `len() >= 32` AND not equal to any documented placeholder
- **Blast radius on invalid**: orchestrator refuses to bind ports; Web UI cannot sign session cookies
- **Validation rule**: `validators.validate_web_ui_cookie_key`
- **Source spec(s)**: 011 audit M-02 (independent cookie-signing key)
- **Note**: Distinct from `SACP_ENCRYPTION_KEY`. A leak of either secret no longer compromises both at-rest API-key encryption AND session-cookie integrity. Rotate by invalidating all active cookies (force re-login) — process restarts already do this since the server-side session store is in-memory.

### `SACP_CONTEXT_MAX_TURNS`

- **Default**: `20`
- **Type**: integer
- **Valid range**: `>= 3` (Constitution §6.7 MVC floor)
- **Blast radius on invalid**: turn-loop context assembly cannot satisfy MVC floor; turns silently truncated
- **Validation rule**: `validators.validate_context_max_turns`
- **Source spec(s)**: 003 §FR-003 (5-priority context allocation)

### `SACP_TRUST_PROXY`

- **Default**: `0`
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"` (anything else is invalid)
- **Blast radius on invalid**: documented IP-binding semantics for participant auth become undefined; security-critical
- **Validation rule**: `validators.validate_trust_proxy`
- **Source spec(s)**: 002 §FR-016 (XFF rightmost trust)

### `SACP_ENABLE_DOCS`

- **Default**: `0`
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"`
- **Blast radius on invalid**: `/docs` / `/redoc` / `/openapi.json` exposure becomes undefined
- **Validation rule**: `validators.validate_enable_docs`
- **Source spec(s)**: 006 §FR-014, CHK014

### `SACP_WEB_UI_INSECURE_COOKIES`

- **Default**: unset (auto-detect from request scheme)
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"`
- **Blast radius on invalid**: cookie Secure flag may downgrade in production
- **Validation rule**: `validators.validate_web_ui_insecure_cookies`
- **Note**: The cookie Secure flag is auto-detected from the request scheme — HTTPS gets Secure, HTTP does not. Behind a TLS-terminating reverse proxy, set `SACP_TRUST_PROXY=1` so the orchestrator honors `X-Forwarded-Proto`. Setting this var to `1` is a force-off override; unnecessary for normal LAN/HTTP use after auto-detect, kept for explicit operator control.
- **Source spec(s)**: 011 §SR cookie classification

### `SACP_WEB_UI_MCP_ORIGIN`

- **Default**: `http://localhost:8750`
- **Type**: URL (single http(s):// entry; first http(s):// in a space-separated list wins)
- **Valid range**: scheme `http` / `https` / `ws` / `wss`; non-empty netloc
- **Blast radius on invalid**: Web UI proxy cannot reach MCP server; SPA's `/api/mcp/*` calls fail with 502
- **Validation rule**: `validators.validate_web_ui_mcp_origin`
- **Source spec(s)**: 011 audit H-02 (same-origin MCP proxy upstream)
- **Note**: After the H-02 same-origin proxy landed this var is server-side only — read by `src/web_ui/proxy.py` to decide where to forward MCP tool calls. The browser never connects to this origin directly; the CSP `connect-src` no longer lists it.

### `SACP_WEB_UI_WS_ORIGIN`

- **Default**: empty (same-origin)
- **Type**: URL (typically `ws://` or `wss://`)
- **Valid range**: scheme `http` / `https` / `ws` / `wss`; non-empty netloc
- **Blast radius on invalid**: WebSocket connection fails on origin check
- **Validation rule**: `validators.validate_web_ui_ws_origin`
- **Source spec(s)**: 011 §FR-014 WS lifecycle

### `SACP_CORS_ORIGINS`

- **Default**: empty (deny all cross-origin)
- **Type**: comma-separated URL list
- **Valid range**: each comma-separated entry parses as URL with scheme in {`http`, `https`, `ws`, `wss`} and non-empty netloc
- **Blast radius on invalid**: CORS preflights fail; legitimate browser clients blocked
- **Validation rule**: `validators.validate_cors_origins`
- **Source spec(s)**: 006 §FR (CORS regex)

### `SACP_WEB_UI_ALLOWED_ORIGINS`

- **Default**: empty (same-origin only)
- **Type**: comma-separated URL list
- **Valid range**: same as `SACP_CORS_ORIGINS`
- **Blast radius on invalid**: Web UI rejects legitimate cross-origin connects
- **Validation rule**: `validators.validate_web_ui_allowed_origins`
- **Source spec(s)**: 011 §SR-006 CSRF + origin

### `SACP_WS_MAX_CONNECTIONS_PER_IP`

- **Default**: `10`
- **Type**: positive integer
- **Valid range**: `> 0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_ws_max_connections_per_ip`
- **Source spec(s)**: 011 close-code 4429; audit H-03

### `SACP_MAX_SUBSCRIBERS_PER_SESSION`

- **Default**: `64`
- **Type**: positive integer
- **Valid range**: `> 0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports; SSE subscriber cap uses hardcoded default if unset
- **Validation rule**: `validators.validate_max_subscribers_per_session`
- **Source spec(s)**: 006 §FR-019 (per-session SSE subscriber cap); 006 SC-008

### `SACP_CACHING_ENABLED`

- **Default**: `1`
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"` (anything else is invalid)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports; runtime fallback (if env mutates post-validation) treats unrecognised values as enabled
- **Validation rule**: `validators.validate_caching_enabled`
- **Source spec(s)**: 003 §FR-033 (provider-native cache wiring)
- **Note**: When disabled, dispatch is byte-identical to pre-cache behaviour — no `cache_control` blocks, no `prompt_cache_key`, no `cachedContent` reference. Set to `0` to A/B compare or to disable cache writes during a probe.

### `SACP_ANTHROPIC_CACHE_TTL`

- **Default**: `1h`
- **Type**: enum
- **Valid range**: `"5m"` or `"1h"`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports; runtime fallback uses `1h`
- **Validation rule**: `validators.validate_anthropic_cache_ttl`
- **Source spec(s)**: 003 §FR-033
- **Note**: Default is `1h` per the 2026-03-06 silent-default change (Anthropic dropped the implicit 1h TTL to 5m without notice). Multi-minute session cadence retains warm cache hits at the 2x cache-write surcharge, recovered after the third read.

### `SACP_OPENAI_CACHE_RETENTION`

- **Default**: `default`
- **Type**: enum
- **Valid range**: `"default"` or `"24h"`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports; runtime fallback uses `default`
- **Validation rule**: `validators.validate_openai_cache_retention`
- **Source spec(s)**: 003 §FR-033
- **Note**: `24h` is OpenAI Extended Prompt Caching (`prompt_cache_retention="24h"`); only applied to models in the bridge-side allowlist. The Phase 1 allowlist is empty by design — parameter wiring ships now; model activation lands when production traffic confirms availability.

### `SACP_DENSITY_ANOMALY_RATIO`

- **Default**: `1.5`
- **Type**: float
- **Valid range**: `[1.0, 5.0]`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports; runtime fallback uses `1.5`
- **Validation rule**: `validators.validate_density_anomaly_ratio`
- **Source spec(s)**: 004 §FR-020 (information-density anomaly threshold)
- **Note**: Multiplier over the rolling 20-turn density baseline mean. A value of 1.5 means "flag turns whose density is more than 1.5× the recent average." Phase 1 retuning will be informed by `tests/calibration/density_distribution.json` once production sessions accumulate.

## Reserved (documented but not yet wired)

These vars appear in `src/mcp_server/tools/debug.py` `_CONFIG_KEYS` allowlist
(so they show up in debug-export config snapshots if set) but are NOT consumed
by application code. Operators setting them today will see the value in the
debug snapshot but no behavioral effect. Validators land when application code
starts consuming them — likely as part of a per-spec amendment cluster.

### `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS`

- **Default**: `600`
- **Type**: number (seconds)
- **Valid range**: `> 0`
- **Blast radius on invalid**: turn-loop dispatch keeps retrying past the operator-intended ceiling; cascading hangs propagate into next-turn latency
- **Validation rule**: `validators.validate_compound_retry_total_max_seconds`
- **Source spec(s)**: 003 §FR-031 (compound-retry cap)

### `SACP_COMPOUND_RETRY_WARN_FACTOR`

- **Default**: `2.0`
- **Type**: float (multiplier on per-attempt `timeout`)
- **Valid range**: `>= 1.0`
- **Blast radius on invalid**: `compound_retry_warn` log line either fires before the per-attempt timeout (noise) or never (no early signal of pathological cascades)
- **Validation rule**: `validators.validate_compound_retry_warn_factor`
- **Source spec(s)**: 003 §FR-031 (compound-retry warn threshold)
### `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S`

- **Default**: unset (per-turn delivery; current Phase 2 behavior preserved)
- **Type**: integer (seconds)
- **Valid range**: `1 <= value <= 300` (1 second to 5 minutes)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_high_traffic_batch_cadence_s`
- **Source spec(s)**: 013 §FR-001 / FR-003 / SC-002 (broadcast mode mechanism 1)

### `SACP_CONVERGENCE_THRESHOLD_OVERRIDE`

- **Default**: unset (use global `SACP_CONVERGENCE_THRESHOLD` from spec 004)
- **Type**: float
- **Valid range**: `0.0 < value < 1.0` (strict bounds; `0.0` and `1.0` are operator-error states per spec 004 line 111)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_convergence_threshold_override`
- **Source spec(s)**: 013 §FR-005 / FR-007 (broadcast mode mechanism 2)

### `SACP_OBSERVER_DOWNGRADE_THRESHOLDS`

- **Default**: unset (no downgrades; current Phase 2 behavior preserved)
- **Type**: composite key:value string (`participants:N,tpm:N[,restore_window_s:N]`)
- **Valid range**:
  - `participants` — required; integer in `[2, 10]`
  - `tpm` — required; integer in `[1, 600]`
  - `restore_window_s` — optional; integer in `[1, 3600]`; default `120`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports (unparseable; missing required key; unknown key; out-of-range integer)
- **Validation rule**: `validators.validate_observer_downgrade_thresholds`
- **Source spec(s)**: 013 §FR-008 / FR-009 / FR-010 / FR-011 (broadcast mode mechanism 3)

### `SACP_SECURITY_EVENTS_RETENTION_DAYS`

- **Default**: unset (the orchestrator never auto-purges; operator-driven)
- **Type**: integer (days)
- **Valid range**: `> 0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports; purge CLI rejects the value
- **Validation rule**: `validators.validate_security_events_retention_days`
- **Source spec(s)**: 007 §SC-009 (`security_events` 90-day default)
- **Note**: Consumed by `scripts/purge_security_events.py`, an operator-scheduled CLI (cron / Ofelia / k8s CronJob — default cadence daily). The orchestrator itself does NOT auto-purge; absence of the env var means "never delete" until the operator runs the script. Default applied by the script when unset is 90 days per 007 §SC-009.

### `SACP_RATE_LIMIT_PER_MIN`

- **Status**: Reserved
- **Phase 3 trigger**: 009 rate-limiter spec amendment introducing operator-tunable per-minute rate
- **Intended type**: integer, `>= 1`

### `SACP_DEFAULT_TURN_TIMEOUT`

- **Status**: Reserved
- **Phase 3 trigger**: 003 turn-loop spec amendment exposing the per-turn timeout knob
- **Intended type**: integer seconds, `> 0` (current hardcoded default in code is 180 per migration 003)

## CI enforcement

`scripts/check_env_vars.py` (per spec 012 FR-005):

- Scans `src/` for every `os.environ.get("SACP_*")` / `os.environ["SACP_*"]` call
- Asserts every grepped var has a section in this doc
- Asserts every var with a section AND a `Validation rule:` line has a function with that name in `src/config/validators.py`
- Drift fails CI

When adding a new `SACP_*` var:

1. Add `os.environ.get(...)` reading the var in code
2. Write a `validate_<var>()` function in `src/config/validators.py`
3. Append it to `VALIDATORS` tuple in `src/config/validators.py`
4. Add a section to this doc with all six fields (Default, Type, Valid range, Blast radius, Validation rule, Source spec)
5. CI gate confirms the linkage; if anything's missing, the build fails
