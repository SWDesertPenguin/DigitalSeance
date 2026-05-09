# SACP Environment Variable Catalog

Authoritative reference for every `SACP_*` environment variable consumed by the SACP orchestrator and Web UI. Per Constitution §12 V16, every var has a documented type, valid range, and fail-closed behavior on invalid values; the application validates every var at startup BEFORE binding any port and exits with a clear error rather than silently accepting an out-of-range default.

## Conventions

- Every var is prefixed `SACP_`.
- "Default" is the value used when the var is unset; `<required>` indicates no default (process exits non-zero if not set).
- "Validation rule" mirrors the per-var validator function.
- Validation runs at startup before binding any port. An invalid value causes the process to exit with a clear error.
- Smoke check: `python -m src.run_apps --validate-config-only` runs validation only and exits 0/1.

## Validated vars

### `SACP_DATABASE_URL`

- **Default**: `<required>`
- **Type**: PostgreSQL URL (`postgresql://...` or `postgres://...`)
- **Valid range**: scheme must be `postgresql` or `postgres`; netloc (host[:port]) must be non-empty
- **Validation rule**: `validators.validate_database_url`
- **Source spec(s)**: 001 §FR-020 (encryption-at-rest scope), 003 §FR-019 (advisory-lock provider)

### `SACP_ENCRYPTION_KEY`

- **Default**: `<required>`
- **Type**: Fernet key (URL-safe base64)
- **Valid range**: must be a valid Fernet key
- **Validation rule**: `validators.validate_encryption_key`
- **Source spec(s)**: 001 §FR-020, §FR-021

### `SACP_AUTH_LOOKUP_KEY`

- **Default**: `<required>`
- **Type**: high-entropy random string (>= 32 chars)
- **Valid range**: `len() >= 32` AND not equal to any documented placeholder
- **Validation rule**: `validators.validate_auth_lookup_key`
- **Source spec(s)**: 002 audit C-02 (HMAC-keyed token lookup)
- **Note**: Distinct from `SACP_ENCRYPTION_KEY`. Used as the HMAC key for the token-lookup index. Rotate by re-issuing every active token (force re-login).

### `SACP_WEB_UI_COOKIE_KEY`

- **Default**: `<required>`
- **Type**: high-entropy random string (>= 32 chars)
- **Valid range**: `len() >= 32` AND not equal to any documented placeholder
- **Validation rule**: `validators.validate_web_ui_cookie_key`
- **Source spec(s)**: 011 audit M-02 (independent cookie-signing key)
- **Note**: Distinct from `SACP_ENCRYPTION_KEY`. A leak of either secret no longer compromises both at-rest API-key encryption AND session-cookie integrity. Rotate by invalidating all active cookies (force re-login) — process restarts already do this since the server-side session store is in-memory.

### `SACP_CONTEXT_MAX_TURNS`

- **Default**: `20`
- **Type**: integer
- **Valid range**: `>= 3` (Constitution §6.7 MVC floor)
- **Validation rule**: `validators.validate_context_max_turns`
- **Source spec(s)**: 003 §FR-003 (5-priority context allocation)

### `SACP_TRUST_PROXY`

- **Default**: `0`
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"` (anything else is invalid)
- **Validation rule**: `validators.validate_trust_proxy`
- **Source spec(s)**: 002 §FR-016 (XFF rightmost trust)

### `SACP_ENABLE_DOCS`

- **Default**: `0`
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"`
- **Validation rule**: `validators.validate_enable_docs`
- **Source spec(s)**: 006 §FR-014, CHK014

### `SACP_WEB_UI_INSECURE_COOKIES`

- **Default**: unset (auto-detect from request scheme)
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"`
- **Validation rule**: `validators.validate_web_ui_insecure_cookies`
- **Note**: The cookie Secure flag is auto-detected from the request scheme — HTTPS gets Secure, HTTP does not. Behind a TLS-terminating reverse proxy, set `SACP_TRUST_PROXY=1` so the orchestrator honors `X-Forwarded-Proto`. Setting this var to `1` is a force-off override; unnecessary for normal LAN/HTTP use after auto-detect, kept for explicit operator control.
- **Source spec(s)**: 011 §SR cookie classification

### `SACP_WEB_UI_MCP_ORIGIN`

- **Default**: `http://localhost:8750`
- **Type**: URL (single http(s):// entry; first http(s):// in a space-separated list wins)
- **Valid range**: scheme `http` / `https` / `ws` / `wss`; non-empty netloc
- **Validation rule**: `validators.validate_web_ui_mcp_origin`
- **Source spec(s)**: 011 audit H-02 (same-origin MCP proxy upstream)
- **Note**: Server-side only — read by the MCP proxy module to decide where to forward tool calls. The browser never connects to this origin directly; the CSP `connect-src` no longer lists it.

### `SACP_WEB_UI_WS_ORIGIN`

- **Default**: empty (same-origin)
- **Type**: URL (typically `ws://` or `wss://`)
- **Valid range**: scheme `http` / `https` / `ws` / `wss`; non-empty netloc
- **Validation rule**: `validators.validate_web_ui_ws_origin`
- **Source spec(s)**: 011 §FR-014 WS lifecycle

### `SACP_CORS_ORIGINS`

- **Default**: empty (deny all cross-origin)
- **Type**: comma-separated URL list
- **Valid range**: each comma-separated entry parses as URL with scheme in {`http`, `https`, `ws`, `wss`} and non-empty netloc
- **Validation rule**: `validators.validate_cors_origins`
- **Source spec(s)**: 006 §FR (CORS regex)

### `SACP_WEB_UI_ALLOWED_ORIGINS`

- **Default**: empty (same-origin only)
- **Type**: comma-separated URL list
- **Valid range**: same as `SACP_CORS_ORIGINS`
- **Validation rule**: `validators.validate_web_ui_allowed_origins`
- **Source spec(s)**: 011 §SR-006 CSRF + origin

### `SACP_WS_MAX_CONNECTIONS_PER_IP`

- **Default**: `10`
- **Type**: positive integer
- **Valid range**: `> 0`
- **Validation rule**: `validators.validate_ws_max_connections_per_ip`
- **Source spec(s)**: 011 audit H-03

### `SACP_MAX_SUBSCRIBERS_PER_SESSION`

- **Default**: `64`
- **Type**: positive integer
- **Valid range**: `> 0`
- **Validation rule**: `validators.validate_max_subscribers_per_session`
- **Source spec(s)**: 006 §FR-019 (per-session SSE subscriber cap); 006 SC-008

### `SACP_CACHING_ENABLED`

- **Default**: `1`
- **Type**: bool-string enum
- **Valid range**: `"0"` or `"1"` (anything else is invalid)
- **Validation rule**: `validators.validate_caching_enabled`
- **Source spec(s)**: 003 §FR-033 (provider-native cache wiring)
- **Note**: When disabled, dispatch is byte-identical to pre-cache behaviour — no `cache_control` blocks, no `prompt_cache_key`, no `cachedContent` reference. Set to `0` to A/B compare or to disable cache writes during a probe.

### `SACP_ANTHROPIC_CACHE_TTL`

- **Default**: `1h`
- **Type**: enum
- **Valid range**: `"5m"` or `"1h"`
- **Validation rule**: `validators.validate_anthropic_cache_ttl`
- **Source spec(s)**: 003 §FR-033
- **Note**: Default is `1h` per the 2026-03-06 silent-default change (Anthropic dropped the implicit 1h TTL to 5m without notice). Multi-minute session cadence retains warm cache hits at the 2x cache-write surcharge, recovered after the third read.

### `SACP_OPENAI_CACHE_RETENTION`

- **Default**: `default`
- **Type**: enum
- **Valid range**: `"default"` or `"24h"`
- **Validation rule**: `validators.validate_openai_cache_retention`
- **Source spec(s)**: 003 §FR-033
- **Note**: `24h` is OpenAI Extended Prompt Caching (`prompt_cache_retention="24h"`); only applied to models in the bridge-side allowlist. The Phase 1 allowlist is empty by design — parameter wiring ships now; model activation lands when production traffic confirms availability.

### `SACP_DENSITY_ANOMALY_RATIO`

- **Default**: `1.5`
- **Type**: float
- **Valid range**: `[1.0, 5.0]`
- **Validation rule**: `validators.validate_density_anomaly_ratio`
- **Source spec(s)**: 004 §FR-020 (information-density anomaly threshold)
- **Note**: Multiplier over the rolling 20-turn density baseline mean. A value of 1.5 means "flag turns whose density is more than 1.5× the recent average." Phase 1 retuning will be informed by `tests/calibration/density_distribution.json` once production sessions accumulate.

### `SACP_NETWORK_RATELIMIT_ENABLED`

- **Default**: `false`
- **Type**: boolean (string `"true"`/`"false"`, case-insensitive; `"1"`/`"0"` accepted)
- **Valid range**: exactly `true` or `false` (after case-folding) — equivalently `1` or `0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_network_ratelimit_enabled`
- **Source spec(s)**: 019 §FR-001 / FR-014 (master switch for the per-IP network rate limiter)
- **Note**: When `false` (the default), the middleware is NOT registered and pre-feature behavior is preserved byte-identically (SC-006). When `true`, the middleware is registered FIRST per FR-001 and FR-002 and `SACP_NETWORK_RATELIMIT_RPM` becomes required (cross-validator constraint enforced by `validate_network_ratelimit_rpm`).

### `SACP_NETWORK_RATELIMIT_RPM`

- **Default**: `60`
- **Type**: positive integer (requests per minute)
- **Valid range**: `1 <= value <= 6000`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_network_ratelimit_rpm`
- **Source spec(s)**: 019 §FR-003 (steady-state per-IP token-bucket refill rate)
- **Note**: Steady-state requests-per-minute admitted per source IP. Default 60 = one request per second on average per IP — generous for human-driven MCP clients. Operator tunes upward for NAT-fronted traffic.
- **Cross-validator constraint**: when `SACP_NETWORK_RATELIMIT_ENABLED=true` AND this is unset, V16 fails with a message naming the var (the limiter requires a budget to be useful). Enforced by `validate_network_ratelimit_rpm`.

### `SACP_NETWORK_RATELIMIT_BURST`

- **Default**: `15` (= `RPM / 4` rounded; allows ~15-second bursts at the steady-state rate)
- **Type**: positive integer (tokens)
- **Valid range**: `1 <= value <= 10000`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_network_ratelimit_burst`
- **Source spec(s)**: 019 §FR-003 (token-bucket burst capacity)
- **Note**: Token-bucket capacity. Allows short bursts above the steady-state RPM. Default 15 (= 60/4) means a quiet-then-active client can spike up to 15 requests in a quarter-minute before the steady-state rate kicks in. Operators raising RPM should typically raise BURST proportionally.

### `SACP_NETWORK_RATELIMIT_TRUST_FORWARDED_HEADERS`

- **Default**: `false`
- **Type**: boolean (string `"true"`/`"false"`, case-insensitive; `"1"`/`"0"` accepted)
- **Valid range**: exactly `true` or `false` (after case-folding) — equivalently `1` or `0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_network_ratelimit_trust_forwarded_headers`
- **Source spec(s)**: 019 §FR-011 (RFC 7239 `Forwarded` / `X-Forwarded-For` opt-in)
- **Note**: Trust-by-opt-in for forwarded-header parsing. When `false` (default), the middleware uses the immediate peer IP and ignores `Forwarded` (RFC 7239) and `X-Forwarded-For` headers. When `true`, the middleware parses the rightmost-trusted entry of `Forwarded` (preferred) or `X-Forwarded-For` (fallback). The operator is responsible for ensuring the upstream proxy sanitizes inbound headers before forwarding — otherwise the limiter can be bypassed via spoofed headers.

### `SACP_NETWORK_RATELIMIT_MAX_KEYS`

- **Default**: `100000`
- **Type**: positive integer (count of distinct keyed-IP entries held in memory)
- **Valid range**: `1024 <= value <= 1_000_000`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_network_ratelimit_max_keys`
- **Source spec(s)**: 019 §FR-004 (memory bound on the per-IP budget map)
- **Note**: LRU bound on the per-IP budget map. When the map exceeds this size, the least-recently-accessed entry is evicted via `OrderedDict.popitem(last=False)` (O(1) amortized). Memory bound is `MAX_KEYS × ~300 bytes per entry`; default 100k = ~30MB worst case. Raise toward 1M for deployments with high IP diversity (public-internet-exposed, or NAT-egress-fronted with many client IPs).
### `SACP_FILLER_THRESHOLD`

- **Default**: unset (per-family default from the `BehavioralProfile` dict in `src/orchestrator/shaping.py` applies — anthropic/openai default `0.60`; gemini/groq/ollama/vllm default `0.55`)
- **Type**: float
- **Valid range**: `0.0 <= value <= 1.0` (inclusive). Values near `0.0` flag almost every draft; values near `1.0` flag almost nothing. When set, this env var overrides the per-family default uniformly across all six provider families.
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_filler_threshold`
- **Source spec(s)**: 021 §FR-002 / FR-003 / FR-004 (filler-scorer aggregate threshold)
- **Note**: Operators tune this against observed retry-firing rate per provider family (per `quickstart.md` Step 2). Per-family thresholds are not env-tunable in v1 — that surface lands via a Constitution §14.2 amendment when session experience justifies it.

### `SACP_REGISTER_DEFAULT`

- **Default**: `2` (Conversational)
- **Type**: integer
- **Valid range**: `1` (Direct), `2` (Conversational), `3` (Balanced), `4` (Technical), `5` (Academic). Inclusive bounds.
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_register_default`
- **Source spec(s)**: 021 §FR-009 / FR-010 (initial session-row fallback when no `session_register` row exists)
- **Note**: Applied as the session-level slider when no facilitator has set one for a session. Once a facilitator sets the slider, the `session_register` row supersedes this default.

### `SACP_RESPONSE_SHAPING_ENABLED`

- **Default**: `false` — the master switch ships off so deployments opt in explicitly
- **Type**: boolean
- **Valid range**: `"true"` or `"false"` (case-insensitive); `"1"` or `"0"` accepted per existing validator convention
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_response_shaping_enabled`
- **Source spec(s)**: 021 §FR-005 / SC-002 (master switch for the filler-scorer + retry pipeline)
- **Note**: Setting this var to `false` MUST disable the entire filler-scorer + retry pipeline; pre-feature acceptance tests pass byte-identically (SC-002 regression contract). The register slider is independent of this switch — slider deltas always emit regardless of master-switch state, since the slider is a prompt-composition concern not a shaping concern (spec edge case).

## Reserved (documented but not yet wired)

These vars appear in the debug-export config snapshot allowlist but are NOT consumed by application code. Operators setting them today will see the value in the debug snapshot but no behavioral effect. Validators land when application code starts consuming them — likely as part of a per-spec amendment cluster.

### `SACP_COMPOUND_RETRY_TOTAL_MAX_SECONDS`

- **Default**: `600`
- **Type**: number (seconds)
- **Valid range**: `> 0`
- **Validation rule**: `validators.validate_compound_retry_total_max_seconds`
- **Source spec(s)**: 003 §FR-031 (compound-retry cap)

### `SACP_COMPOUND_RETRY_WARN_FACTOR`

- **Default**: `2.0`
- **Type**: float (multiplier on per-attempt `timeout`)
- **Valid range**: `>= 1.0`
- **Validation rule**: `validators.validate_compound_retry_warn_factor`
- **Source spec(s)**: 003 §FR-031 (compound-retry warn threshold)

### `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S`

- **Default**: unset (per-turn delivery; current Phase 2 behavior preserved)
- **Type**: integer (seconds)
- **Valid range**: `1 <= value <= 300` (1 second to 5 minutes)
- **Validation rule**: `validators.validate_high_traffic_batch_cadence_s`
- **Source spec(s)**: 013 §FR-001 / FR-003 / SC-002 (broadcast mode mechanism 1)

### `SACP_CONVERGENCE_THRESHOLD_OVERRIDE`

- **Default**: unset (use global convergence threshold from spec 004)
- **Type**: float
- **Valid range**: `0.0 < value < 1.0` (strict bounds)
- **Validation rule**: `validators.validate_convergence_threshold_override`
- **Source spec(s)**: 013 §FR-005 / FR-007 (broadcast mode mechanism 2)

### `SACP_OBSERVER_DOWNGRADE_THRESHOLDS`

- **Default**: unset (no downgrades; current Phase 2 behavior preserved)
- **Type**: composite key:value string (`participants:N,tpm:N[,restore_window_s:N]`)
- **Valid range**:
  - `participants` — required; integer in `[2, 10]`
  - `tpm` — required; integer in `[1, 600]`
  - `restore_window_s` — optional; integer in `[1, 3600]`; default `120`
- **Validation rule**: `validators.validate_observer_downgrade_thresholds`
- **Source spec(s)**: 013 §FR-008 / FR-009 / FR-010 / FR-011 (broadcast mode mechanism 3)

### `SACP_DMA_TURN_RATE_THRESHOLD_TPM`

- **Default**: unset (turn-rate signal does not contribute to controller decisions)
- **Type**: integer (turns per minute)
- **Valid range**: `1 <= value <= 600`
- **Validation rule**: `validators.validate_dma_turn_rate_threshold_tpm`
- **Source spec(s)**: 014 §FR-003 / FR-004 (signal source: turns/minute over the 5-minute observation window)

### `SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD`

- **Default**: unset (convergence-derivative signal does not contribute)
- **Type**: float (per-window absolute derivative magnitude of the similarity score)
- **Valid range**: `0.0 < value <= 1.0`
- **Validation rule**: `validators.validate_dma_convergence_derivative_threshold`
- **Source spec(s)**: 014 §FR-003 / FR-004

### `SACP_DMA_QUEUE_DEPTH_THRESHOLD`

- **Default**: unset (queue-depth signal does not contribute)
- **Type**: integer (count of pending messages across human-side batch queues per session)
- **Valid range**: `1 <= value <= 1000`
- **Validation rule**: `validators.validate_dma_queue_depth_threshold`
- **Source spec(s)**: 014 §FR-003 / FR-004 (soft dependency on spec-013 batching; signal is inactive when batching is unconfigured)

### `SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD`

- **Default**: unset (density-anomaly signal does not contribute)
- **Type**: integer (count of density-anomaly-flagged turns per observation-window minute)
- **Valid range**: `1 <= value <= 60`
- **Validation rule**: `validators.validate_dma_density_anomaly_rate_threshold`
- **Source spec(s)**: 014 §FR-003 / FR-004

### `SACP_DMA_DWELL_TIME_S`

- **Default**: unset (allowed in advisory mode; required when `SACP_AUTO_MODE_ENABLED=true`)
- **Type**: integer (seconds)
- **Valid range**: `30 <= value <= 1800` (30 s practical floor; 30 minutes sanity ceiling)
- **Validation rule**: `validators.validate_dma_dwell_time_s`
- **Source spec(s)**: 014 §FR-007 / FR-010
- **Cross-validator constraint**: when `SACP_AUTO_MODE_ENABLED=true` AND this is unset, V16 fails with a message naming both vars (FR-010 — auto-apply without a dwell floor is flap-prone). Enforced by `validate_auto_mode_enabled`.

### `SACP_AUTO_MODE_ENABLED`

- **Default**: `false` (advisory mode — controller emits `mode_recommendation` events but never toggles spec-013 mechanisms)
- **Type**: boolean
- **Valid range**: exactly `"true"` or `"false"` (case-sensitive). Unset is treated as `false`.
- **Validation rule**: `validators.validate_auto_mode_enabled`
- **Source spec(s)**: 014 §FR-006 / FR-010 / FR-011
- **Note**: Setting this to `true` requires prior advisory-mode validation per the spec User Story priority ordering (Story 1 P1 advisory → Story 2 P2 auto-apply). Enabling auto-apply without first observing the controller's signal interpretation across multiple sessions is an operator-trust hazard; the spec deliberately defaults to `false` so production deployments are advisory-only until the operator opts in.

### `SACP_SECURITY_EVENTS_RETENTION_DAYS`

- **Default**: unset (the orchestrator never auto-purges; operator-driven)
- **Type**: integer (days)
- **Valid range**: `> 0`
- **Validation rule**: `validators.validate_security_events_retention_days`
- **Source spec(s)**: 007 §SC-009 (`security_events` 90-day default)
- **Note**: Consumed by `scripts/purge_security_events.py`, an operator-scheduled CLI (cron / Ofelia / k8s CronJob — default cadence daily). The orchestrator itself does NOT auto-purge; absence of the env var means "never delete" until the operator runs the script. Default applied by the script when unset is 90 days per 007 §SC-009.

### `SACP_LENGTH_CAP_DEFAULT_KIND`

- **Default**: `none`
- **Type**: string enum
- **Valid range**: `none` | `time` | `turns` | `both`
- **Validation rule**: `validators.validate_sacp_length_cap_default_kind`
- **Source spec(s)**: 025 §FR-024
- **Note**: Deployment-wide default for new sessions. Existing sessions are unaffected. The facilitator can always override per-session at session-create.

### `SACP_LENGTH_CAP_DEFAULT_SECONDS`

- **Default**: unset (no default time cap)
- **Type**: integer (seconds), or empty
- **Valid range**: `[60, 2_592_000]` (1 minute to 30 days) when set
- **Validation rule**: `validators.validate_sacp_length_cap_default_seconds`
- **Source spec(s)**: 025 §FR-024
- **Note**: Inherited by new sessions when `SACP_LENGTH_CAP_DEFAULT_KIND` is `time` or `both`. Empty is allowed; the facilitator must specify on session-create when the inherited kind requires it.

### `SACP_LENGTH_CAP_DEFAULT_TURNS`

- **Default**: unset (no default turn cap)
- **Type**: integer, or empty
- **Valid range**: `[1, 10_000]` when set
- **Validation rule**: `validators.validate_sacp_length_cap_default_turns`
- **Source spec(s)**: 025 §FR-024
- **Note**: Inherited by new sessions when `SACP_LENGTH_CAP_DEFAULT_KIND` is `turns` or `both`. Empty is allowed.

### `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION`

- **Default**: `0.80`
- **Type**: float
- **Valid range**: strict `(0.0, 1.0)` — both endpoints excluded
- **Validation rule**: `validators.validate_sacp_conclude_phase_trigger_fraction`
- **Source spec(s)**: 025 §FR-005
- **Note**: Applies to all sessions, not per-session. Lower values trigger conclude earlier; higher closer to 100%. The exclusive range protects against pathological configurations: 0.0 means "always concluding", 1.0 means "no conclude phase, hard stop only".

### `SACP_CONCLUDE_PHASE_PROMPT_TIER`

- **Default**: `4`
- **Type**: integer
- **Valid range**: `{1, 2, 3, 4}` (matches spec 008's tier set)
- **Validation rule**: `validators.validate_sacp_conclude_phase_prompt_tier`
- **Source spec(s)**: 025 §FR-008
- **Note**: Applies to all sessions. Default Tier 4 is the only tier reliably present (every participant's prompt assembly reaches Tier 4 if they have any custom_prompt OR any spec 021 register-slider delta). Operators with custom tier semantics may attach earlier.

### `SACP_PROVIDER_ADAPTER`

- **Default**: `litellm`
- **Type**: string, adapter name from `AdapterRegistry`. Case-folded to lowercase before lookup.
- **Valid range**: any name registered in `AdapterRegistry`. v1 ships `litellm` and `mock`; future provider-specific adapters extend this set in their landing PRs.
- **Validation rule**: `validators.validate_provider_adapter`
- **Source spec(s)**: 020 §FR-002 / FR-003 / SC-005
- **Note**: Process-wide and immutable for the process lifetime per FR-002. Mid-process adapter swap is OUT OF SCOPE per FR-015. An invalid value causes startup exit with an error listing registered names per V16 fail-closed.

### `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`

- **Default**: unset. Required only when `SACP_PROVIDER_ADAPTER=mock`; ignored otherwise.
- **Type**: filesystem path to a JSON fixture file
- **Valid range**: must be a readable file path with valid JSON content matching the schema in `specs/020-provider-adapter-abstraction/contracts/mock-fixtures.md`
- **Validation rule**: `validators.validate_provider_adapter_mock_fixtures_path`
- **Source spec(s)**: 020 §FR-006 / FR-007 / SC-004
- **Note**: Cross-validator dependency on `SACP_PROVIDER_ADAPTER` — when the adapter is `mock`, the path MUST be set + readable + JSON-parseable; when the adapter is any other value, this var is ignored entirely. Same shape as the spec 014 `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` precedent.

### `SACP_RATE_LIMIT_PER_MIN`

- **Status**: Reserved
- **Phase 3 trigger**: 009 rate-limiter spec amendment introducing operator-tunable per-minute rate
- **Intended type**: integer, `>= 1`

### `SACP_DEFAULT_TURN_TIMEOUT`

- **Status**: Reserved
- **Phase 3 trigger**: 003 turn-loop spec amendment exposing the per-turn timeout knob
- **Intended type**: integer seconds, `> 0`

## CI enforcement

`scripts/check_env_vars.py` (per spec 012 FR-005):

- Scans `src/` for every `os.environ.get("SACP_*")` / `os.environ["SACP_*"]` call
- Asserts every grepped var has a section in this doc
- Asserts every var with a section AND a `Validation rule:` line has a corresponding validator function in `src/config/validators.py`
- Drift fails CI

When adding a new `SACP_*` var:

1. Add `os.environ.get(...)` reading the var in code
2. Write a `validate_<var>()` function in `src/config/validators.py`
3. Append it to `VALIDATORS` tuple in `src/config/validators.py`
4. Add a section to this doc with all five fields (Default, Type, Valid range, Validation rule, Source spec)
5. CI gate confirms the linkage; if anything's missing, the build fails
