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
- **Source spec(s)**: 003 §FR-033, 026 FR-001 (formalises Layer 1 wiring)
- **Note**: Default is `1h` per the 2026-03-06 silent-default change (Anthropic dropped the implicit 1h TTL to 5m without notice). Multi-minute session cadence retains warm cache hits at the 2x cache-write surcharge, recovered after the third read.
- **Spec 026 rename reconciliation**: the spec 026 drafted name was `SACP_CACHE_ANTHROPIC_TTL`; the shipped name is `SACP_ANTHROPIC_CACHE_TTL` (this section). Operators searching for either find this doc — both names refer to the same var per [research.md §2](../specs/026-context-compression/research.md).

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
- **Source spec(s)**: 004 §FR-020 (information-density anomaly threshold); 026 FR-018 (formalised Phase 1 signal + summarizer corpus filter)
- **Note**: Multiplier over the rolling 20-turn density baseline mean. A value of 1.5 means "flag turns whose density is more than 1.5x the recent average." Phase 1 retuning will be informed by `tests/calibration/density_distribution.json` once production sessions accumulate.
- **Spec 026 rename reconciliation**: the spec 026 drafted name was `SACP_INFORMATION_DENSITY_THRESHOLD`; the shipped name is `SACP_DENSITY_ANOMALY_RATIO` (this section). Operators searching for either find this doc per [research.md §2](../specs/026-context-compression/research.md).

### `SACP_CACHE_OPENAI_KEY_STRATEGY`

- **Default**: `session_id`
- **Type**: enum
- **Valid range**: `"session_id"` or `"participant_id"`
- **Validation rule**: `validators.validate_cache_openai_key_strategy`
- **Source spec(s)**: 026 FR-001
- **Note**: Routing strategy for OpenAI `prompt_cache_key`. `session_id` keeps a session's per-participant fan-out on the same backend for maximum cache hit-rate. `participant_id` partitions per participant for operators who explicitly want that. Flipping the value invalidates all existing OpenAI cache prefixes; expect a one-cycle miss spike on flip.

### `SACP_COMPRESSION_PHASE2_ENABLED`

- **Default**: `false`
- **Type**: enum (string)
- **Valid range**: `"true"` or `"false"`
- **Validation rule**: `validators.validate_compression_phase2_enabled`
- **Source spec(s)**: 026 FR-008
- **Note**: Phase 2 master switch. When `false` (default), Phase 2 compressors (`llmlingua2_mbert`, `selective_context`) raise `NotImplementedError` on dispatch. When `true`, the dispatch path can route to them per `SACP_COMPRESSION_DEFAULT_COMPRESSOR` or `sessions.compression_mode`. Flipping to `true` requires the optional `compression-phase2` extra installed (`uv pip install -e .[compression-phase2]`); absence raises `NotImplementedError` at first dispatch and the CompressorService fails soft to un-compressed payload per FR-020.
- **Cross-validator interaction**: with `SACP_COMPRESSION_DEFAULT_COMPRESSOR` set to a Phase 2 compressor (`llmlingua2_mbert` or `selective_context`), this MUST be `true` or startup exits with a ValidationFailure naming both vars.

### `SACP_COMPRESSION_THRESHOLD_TOKENS`

- **Default**: `4000`
- **Type**: positive integer
- **Valid range**: `[500, 100000]`
- **Validation rule**: `validators.validate_compression_threshold_tokens`
- **Source spec(s)**: 026 FR-016
- **Note**: Hard-compression engagement threshold. When the outgoing window's projected token count (per the target provider's TokenizerAdapter) exceeds this value, the dispatch path invokes the configured compressor instead of NoOp. Default `4000` is the literature default for LLMLingua-2 mBERT on English prose. Below 500 makes compression overhead dominate any savings; above 100000 effectively disables compression for all real workloads.

### `SACP_LLMLINGUA_MODEL`

- **Status**: Reserved — no startup validator; defensive fall-back to default at load time
- **Default**: `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`
- **Type**: string (Hugging Face checkpoint identifier or local model path)
- **Valid range**: any string accepted by the `llmlingua.PromptCompressor` model loader
- **Source spec(s)**: 026 FR-008 (Phase 2 Layer 4)
- **Note**: Override hook for operators on air-gapped stacks who mirror the LLMLingua-2 mBERT checkpoint locally OR want to point at a fine-tuned SafeTensors-only weights bundle. Reserved — not a master switch; the dispatch path's gating is `SACP_COMPRESSION_PHASE2_ENABLED` + the `compression-phase2` extra. Unset / empty value falls back to the published Microsoft checkpoint above. Lazy-loaded on first compress dispatch; per-process singleton.

### `SACP_COMPRESSION_DEFAULT_COMPRESSOR`

- **Default**: `noop`
- **Type**: enum (string)
- **Valid range**: `"noop"`, `"llmlingua2_mbert"`, `"selective_context"`, `"provence"`, `"layer6"`
- **Validation rule**: `validators.validate_compression_default_compressor`
- **Source spec(s)**: 026 FR-006, FR-007
- **Note**: Default compressor id used when `sessions.compression_mode='auto'`. Phase 1 default is `noop`; Phase 2 cutover is one env-var flip to `llmlingua2_mbert` per SC-007. Out-of-set values exit at startup with the list of registered names. `provence` and `layer6` are Phase 3 scaffolds — selecting them in Phase 1 causes dispatches to fail-soft per FR-020 (the scaffold raises NotImplementedError and the dispatch falls through to un-compressed payload).
- **Cross-validator interaction**: `SACP_COMPRESSION_PHASE2_ENABLED=false` AND this set to a Phase 2 compressor is a ValidationFailure (impossible combo). `SACP_TOPOLOGY=7` AND this NOT equal to `noop` is a ValidationFailure (topology 7 supports Layer 1 caching only).

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

### `SACP_AUDIT_VIEWER_ENABLED`

- **Default**: `false`
- **Type**: boolean (string `"true"`/`"false"`, case-insensitive; `"1"`/`"0"` accepted)
- **Valid range**: exactly `true` or `false` (after case-folding) — equivalently `1` or `0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_audit_viewer_enabled`
- **Source spec(s)**: 029 §FR-018 (master switch for the human-readable audit log viewer surface)
- **Note**: When `false` (the default), the `GET /tools/admin/audit_log` route is NOT mounted and ALL callers receive `HTTP 404` per FR-018. The `audit_log_appended` WebSocket broadcast also remains dormant. Setting to `true` mounts the route and enables the live broadcast helper at `src/repositories/log_repo.py:append_audit_event`. The underlying `admin_audit_log` writes occur regardless of this switch — the surface is gated, not the durable record.

### `SACP_AUDIT_VIEWER_PAGE_SIZE`

- **Default**: `50`
- **Type**: positive integer (rows per page)
- **Valid range**: `10 <= value <= 500` (inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_audit_viewer_page_size`
- **Source spec(s)**: 029 §FR-005 / FR-017 (offset-based pagination cap for the audit log viewer endpoint)
- **Note**: Caps the `limit` query parameter on `GET /tools/admin/audit_log`. Callers may request smaller pages; values above this ceiling (or above `500` regardless) return `HTTP 400`. Default 50 balances render latency on the SPA against round-trip count for typical session lengths (1k+ audit rows scrolled in pages of 50).

### `SACP_AUDIT_VIEWER_RETENTION_DAYS`

- **Default**: unset (no retention WHERE clause; the viewer renders every row in `admin_audit_log` for the session)
- **Type**: integer (days), or empty
- **Valid range**: `1 <= value <= 36500` (1 day to 100 years) when set
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_audit_viewer_retention_days`
- **Source spec(s)**: 029 §FR-016 / FR-017 (display-only retention cap for the audit log viewer)
- **Note**: When set, the endpoint applies `WHERE timestamp >= NOW() - INTERVAL 'N days'` to both the rows and `total_count` queries. Retention applies to viewer DISPLAY only — the underlying `admin_audit_log` table is untouched (durable indefinitely per spec 001 §FR-019) and remains queryable via spec 010 debug-export.

### `SACP_DETECTION_HISTORY_ENABLED`

- **Default**: `false`
- **Type**: boolean (string `"true"`/`"false"`, case-insensitive; `"1"`/`"0"` accepted)
- **Valid range**: exactly `true` or `false` (after case-folding) — equivalently `1` or `0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_detection_history_enabled`
- **Source spec(s)**: 022 §FR-016 (master switch for the detection event history panel surface)
- **Note**: When `false` (the default), neither `GET /tools/admin/detection_events` nor `POST /tools/admin/detection_events/<event_id>/resurface` are mounted and ALL callers receive `HTTP 404`. The `detection_event_appended` and `detection_event_resurfaced` WebSocket broadcasts also remain dormant. Setting to `true` mounts both routes, enables the live broadcast helper, and reveals the "View detection history" entry-point in the facilitator SPA. The underlying detection rows in `routing_log` / `convergence_log` / `admin_audit_log` are written regardless of this switch — the surface is gated, not the durable records.

### `SACP_DETECTION_HISTORY_MAX_EVENTS`

- **Default**: unset (no `LIMIT` on the page query; the endpoint returns all detection events for the session)
- **Type**: positive integer (events), or empty
- **Valid range**: `1 <= value <= 100000` (inclusive) when set
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_detection_history_max_events`
- **Source spec(s)**: 022 §FR-013 (event-count cap on the detection-events endpoint)
- **Note**: Caps the number of rows returned by the page query (newest events kept on cap-hit). Protects against runaway-detector scenarios consuming unbounded UI memory. Operators raising this value should monitor panel-load latency against the V14 budget (P95 ≤ 500ms). Filter axes operate over the loaded set; per-session pushdown is a future enhancement gated on this cap being insufficient for the diagnostic workflow.

### `SACP_DETECTION_HISTORY_RETENTION_DAYS`

- **Default**: unset (no retention WHERE clause; the endpoint renders every event for archived sessions regardless of age)
- **Type**: integer (days), or empty
- **Valid range**: `1 <= value <= 36500` (1 day to 100 years) when set
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_detection_history_retention_days`
- **Source spec(s)**: 022 §FR-014 (display-only retention cap for the detection-events endpoint on archived sessions)
- **Note**: When set, the endpoint applies `WHERE timestamp >= NOW() - INTERVAL 'N days'` to archived-session queries. Active sessions are unaffected (their events are always rendered regardless of this value). Retention applies to viewer DISPLAY only — the underlying `routing_log`, `convergence_log`, and `admin_audit_log` rows are durable indefinitely per spec 001 §FR-019 and remain queryable via spec 010 debug-export.

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

### `SACP_ACCOUNTS_ENABLED`

- **Default**: `0` (master switch ships off; operators opt in)
- **Type**: bool-style enum (`"0"` / `"1"`)
- **Valid range**: exactly `0` or `1`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_accounts_enabled`
- **Source spec(s)**: 023 §FR-018 / FR-022 (master switch for the entire user-account surface)
- **Note**: When `0` (the default), the seven account endpoints (`POST /tools/account/{create,verify,login,email/change,email/verify,password/change,delete}`) AND `GET /me/sessions` AND `POST /me/sessions/{id}/rebind` all return `HTTP 404` and the SPA falls back to the existing token-paste landing per FR-018. When `1`, the account router mounts (subject to `SACP_TOPOLOGY != '7'` per research.md §12). With `1` AND `SACP_EMAIL_TRANSPORT=noop` simultaneously, a startup WARNING is emitted naming the consequence (verification, reset, and notification codes appear in `admin_audit_log` only — not suitable for production). The combination MUST NOT fail-closed since operators legitimately run dev/staging with noop transport.

### `SACP_PASSWORD_ARGON2_TIME_COST`

- **Default**: `2` (OWASP 2024 password-storage cheat-sheet minimum)
- **Type**: positive integer (Argon2id iteration count)
- **Valid range**: `1 <= value <= 10` (inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_password_argon2_time_cost`
- **Source spec(s)**: 023 §FR-003 / FR-022 (Argon2id parameter for new password hashes)
- **Note**: Applies to ALL new password hashes (creation + transparent re-hash on parameter change per SC-007). Existing hashes verify with their stored params. Below `2` is below the OWASP 2024 floor and emits a startup WARNING (NOT a fail-closed exit) — operators on constrained hardware may legitimately run below the floor with the warning logged. Above `10` introduces unacceptable login latency on commodity hardware and refuses to bind.

### `SACP_PASSWORD_ARGON2_MEMORY_COST_KB`

- **Default**: `19456` (19 MiB) per OWASP 2024 password-storage cheat sheet
- **Type**: positive integer (kilobytes)
- **Valid range**: `7168 <= value <= 1048576` (7 MiB to 1 GiB; inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_password_argon2_memory_cost_kb`
- **Source spec(s)**: 023 §FR-003 / FR-022 (Argon2id memory parameter for new password hashes)
- **Note**: Applies to ALL new password hashes. Below `19456` (the OWASP 2024 floor) emits a startup WARNING (operators on constrained hardware accept the warning); below the absolute floor of `7168` refuses to bind outright. Above `1048576` (1 GiB) refuses to bind to prevent memory exhaustion on small instances. The hash format encodes the parameters used at hash time, so transparent re-hash on parameter change is supported via `argon2.PasswordHasher.check_needs_rehash`.

### `SACP_ACCOUNT_SESSION_TTL_HOURS`

- **Default**: `168` (7 days)
- **Type**: positive integer (hours)
- **Valid range**: `1 <= value <= 8760` (1 hour to 1 year; inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_account_session_ttl_hours`
- **Source spec(s)**: 023 §FR-017 / FR-022 (account login session cookie TTL)
- **Note**: Sets the `Max-Age` of the account session cookie issued on login. After expiry, the SPA receives `HTTP 401` on the next session-store-gated request and presents the login flow per spec 011's existing 401 handler. Distinct from the per-session participant token TTL governed by spec 002 — the account cookie sits ABOVE the token in the identity hierarchy.

### `SACP_ACCOUNT_RATE_LIMIT_PER_IP_PER_MIN`

- **Default**: `10`
- **Type**: positive integer (login attempts per IP per minute)
- **Valid range**: `1 <= value <= 1000` (inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_account_rate_limit_per_ip_per_min`
- **Source spec(s)**: 023 §FR-015 / FR-022 (per-IP rate limiter for /tools/account/login + /tools/account/create)
- **Note**: Applies to `POST /tools/account/login` and `POST /tools/account/create` only — narrowly targeting credential-stuffing attacks on the account surface. Composes ADDITIVELY with spec 019's general per-IP network-layer rate limiter (`SACP_NETWORK_RATELIMIT_RPM`); the two limiters do not share state and either tripping wins. Below `1` disables the limiter (rejected); above `1000` the limiter is essentially absent. Limit exceedance returns `HTTP 429` with `Retry-After` mirroring spec 009 §FR-002 / FR-003 shape.

### `SACP_EMAIL_TRANSPORT`

- **Default**: `noop` (development-friendly; codes appear in `admin_audit_log` only)
- **Type**: string enum
- **Valid range**: `noop` | `smtp` | `ses` | `sendgrid`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_email_transport`
- **Source spec(s)**: 023 §FR-022 / Configuration (V16) section (email transport adapter selection)
- **Note**: Selects the `EmailTransport` adapter at startup. v1 ships only the `noop` adapter; the other three values pass SYNTACTIC validation here but the adapter factory raises `NotImplementedError` at startup with a pointer to `specs/023-user-accounts/contracts/email-transport.md`. Operators needing real transport should defer enabling accounts until the follow-up email-transport spec ships. When `SACP_ACCOUNTS_ENABLED=1` AND this value is `noop` simultaneously, a startup WARNING is emitted (NOT a fail-closed exit) per FR-022 — verification, reset, and notification codes appear in `admin_audit_log` only and are NOT suitable for production.

### `SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`

- **Default**: `7`
- **Type**: non-negative integer (days)
- **Valid range**: `0 <= value <= 365` (inclusive). The value `0` disables the grace period entirely (immediate email release on deletion).
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_account_deletion_email_grace_days`
- **Source spec(s)**: 023 §FR-013 / FR-022 (email reservation window after account deletion)
- **Note**: Read at deletion time to populate `accounts.email_grace_release_at = deleted_at + (value * interval '1 day')`. Re-registration with the same email is rejected during the grace window per FR-013; after `now() > email_grace_release_at` the email is releasable for fresh registration. Operators with stricter retention policies set this lower (or to `0` for immediate release); operators with longer retention windows set this higher up to one year.

### `SACP_DEPLOYMENT_OWNER_KEY`

- **Default**: empty (unset → ownership-transfer endpoint refuses every request)
- **Type**: string (high-entropy random secret) or empty
- **Valid range**: empty OR length `>= 32` chars; values containing placeholder fragments (`example`, `replace`, `change-me`, etc.) are rejected
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_deployment_owner_key`
- **Source spec(s)**: 023 §FR-020 / research §7 (revised at impl-time to ship in v1)
- **Note**: Gates `POST /tools/admin/account/transfer_participants` per spec 023 FR-020. When unset, the endpoint refuses every request — the admin-auth shim has no key to compare against. When set, callers attach the same value as the `X-Deployment-Owner-Key` header on the transfer request. The shim is intentionally minimal: a single static key. Future operator-auth specs (mTLS, OAuth M2M) replace the dependency without changing the endpoint contract.


### `SACP_SCRATCH_ENABLED`

- **Default**: `0` (off — opt-in master switch ships disabled)
- **Type**: boolean (`0` or `1`)
- **Valid range**: exactly `0` or `1`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_scratch_enabled`
- **Source spec(s)**: 024 §FR-019 / FR-022 (master switch for the facilitator scratch panel surface)
- **Note**: When `0` (the default), every endpoint under `/tools/facilitator/scratch/` returns HTTP 404 and the SPA does NOT render the scratch panel entry-point button in the session header. When `1`, the scratch router mounts and the entry-point button surfaces (gated additionally by FR-021 facilitator-only role check). Notes data NEVER reaches AI context regardless of this switch — the surface is gated, not the FR-001 isolation guarantee.

### `SACP_SCRATCH_NOTE_MAX_KB`

- **Default**: `64`
- **Type**: positive integer (kilobytes)
- **Valid range**: `1 <= value <= 1024` (1 KiB to 1 MiB inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_scratch_note_max_kb`
- **Source spec(s)**: 024 §FR-010 / FR-022 (per-note size cap)
- **Note**: Per-note content size cap. Notes exceeding the cap are rejected with HTTP 413 from the `POST` and `PUT` scratch-notes endpoints. The cap protects against unbounded notes consuming DB space; raising past 1 MiB is unsupported in v1 (the underlying TEXT column accepts more bytes, but the SPA renderer + autosave-debounce envelope assume bounded inputs).

### `SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE`

- **Default**: unset (indefinite retention; no sweep applies)
- **Type**: positive integer (days), or empty
- **Valid range**: `1 <= value <= 36500` (1 day to 100 years) when set
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_scratch_retention_days_after_archive`
- **Source spec(s)**: 024 §FR-018 / FR-022 (retention sweep for account-scoped notes)
- **Note**: Retention applies to account-scoped notes only (session-scoped notes are deleted on archive regardless of this value per FR-017). The sweep is operator-scheduled via `scripts/scratch_retention_sweep.py`; the orchestrator does NOT auto-purge in-process. Each purged note emits one `admin_audit_log` row with `action=''facilitator_note_purged_retention''`.
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

### `SACP_MOCK_CAPABILITY_SET`

- **Status**: Reserved
- **Phase 3 trigger**: 020 mock-adapter capability-set selection (currently fixture-driven via the default key)
- **Intended type**: string, capability-set key from the loaded mock fixture file
- **Note**: Read by the mock adapter to pick which `capabilities` block applies to a dispatched model; ignored when `SACP_PROVIDER_ADAPTER` is anything other than `mock`. Validator deferred until a downstream consumer requires structured capability-set selection.

### `SACP_TOPOLOGY`

- **Status**: Reserved
- **Phase 3 trigger**: forward-proof gate for topology 7 (MCP-to-MCP) per spec 014 research §7 + spec 020 research §10
- **Intended type**: integer, `1`-`7`
- **Note**: Read but unvalidated in v1. Topology 7 short-circuits provider adapter init (spec 020) and DMA controller spawn (spec 014); other values are no-ops. Wiring + validator land with the topology-7 selector amendment.

### `SACP_RATE_LIMIT_PER_MIN`

- **Status**: Reserved
- **Phase 3 trigger**: 009 rate-limiter spec amendment introducing operator-tunable per-minute rate
- **Intended type**: integer, `>= 1`

### `SACP_DEFAULT_TURN_TIMEOUT`

- **Status**: Reserved
- **Phase 3 trigger**: 003 turn-loop spec amendment exposing the per-turn timeout knob
- **Intended type**: integer seconds, `> 0`

### `SACP_STANDBY_DEFAULT_WAIT_MODE`

- **Default**: `wait_for_human` — newly-INSERTed participant rows inherit this default unless the facilitator or owning human sets `wait_mode` explicitly via the spec 027 `set_wait_mode` endpoint
- **Type**: string enum
- **Valid range**: exactly `wait_for_human` or `always`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_standby_default_wait_mode`
- **Source spec(s)**: 027 §FR-001 / FR-028
- **Note**: Setting this to `always` deployment-wide effectively disables the entire standby feature — every new participant opts out of standby evaluation. The setting affects new INSERTs only; pre-existing rows retain their stored `wait_mode` value. A per-participant change via the FR-025 endpoint always supersedes this default.

### `SACP_STANDBY_FILLER_DETECTION_TURNS`

- **Default**: `5` (consecutive standby cycles)
- **Type**: positive integer
- **Valid range**: `2 <= value <= 100` (inclusive). Below `2` the repetition guard is meaningless (a single cycle would trigger); above `100` the pivot is effectively unreachable in any realistic session.
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_standby_filler_detection_turns`
- **Source spec(s)**: 027 §FR-017 (auto-pivot consecutive-cycle denominator)
- **Note**: The cycle counter increments on every round-robin tick where the participant remained in standby. Resets to 0 on every standby-exit transition (gate clear, manual pause, circuit_open precedence, participant departure). Persisted in `participants.standby_cycle_count` (durable across loop restarts per Session 2026-05-12 Q11).

### `SACP_STANDBY_PIVOT_TIMEOUT_SECONDS`

- **Default**: `600` (10 minutes)
- **Type**: positive integer (seconds)
- **Valid range**: `60 <= value <= 86400` (inclusive — 1 minute to 1 day)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_standby_pivot_timeout_seconds`
- **Source spec(s)**: 027 §FR-017 (auto-pivot minimum elapsed time)
- **Note**: Measured from the timestamp the gating event opened (the unresolved question event was emitted, the review_gate was staged, etc.). Both the cycle-count AND the elapsed-time gates must be satisfied before the pivot can fire. The 60-second floor prevents racing a near-immediate gate clear; the 1-day ceiling caps the maximum wait at one human-business-cycle.

### `SACP_STANDBY_PIVOT_RATE_CAP_PER_SESSION`

- **Default**: `1` pivot per session lifetime
- **Type**: positive integer
- **Valid range**: `0 <= value <= 100` (inclusive). `0` disables auto-pivot entirely (operators who want pure standby with no orchestrator intervention).
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_standby_pivot_rate_cap_per_session`
- **Source spec(s)**: 027 §FR-019 (per-session pivot cap)
- **Note**: When the cap is exhausted, subsequent would-have-pivoted conditions log `routing_log.reason='pivot_skipped_rate_cap'` and the participant remains in standby without the long-term-observer transition firing automatically (FR-020 sub-state requires the pivot to actually fire). Resolved per Session 2026-05-12 Q6 — per-session scope, not per-participant; per-participant capping is a future amendment.

### `SACP_MCP_PROTOCOL_ENABLED`

- **Default**: `false`
- **Type**: bool-string enum (`'true'` / `'false'`, case-sensitive)
- **Valid range**: `'true'` or `'false'` only; any other value exits at startup
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_sacp_mcp_protocol_enabled`
- **Source spec(s)**: 030 Phase 2 FR-034 (MCP Streamable HTTP master switch)
- **Note**: When `'false'` (default), POST /mcp returns HTTP 404. The discovery endpoint `/.well-known/mcp-server` remains active and responds with `{"enabled": false}` per FR-024 + SC-023 so clients can discover the switch state without assuming availability.

### `SACP_MCP_SESSION_IDLE_TIMEOUT_SECONDS`

- **Default**: `1800` (30 minutes)
- **Type**: positive integer (seconds)
- **Valid range**: `60 <= value <= 86400` (inclusive — 1 minute to 1 day)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_sacp_mcp_session_idle_timeout_seconds`
- **Source spec(s)**: 030 Phase 2 FR-034 (MCP session idle expiry)
- **Note**: When a session has received no requests for this many seconds, the next request returns HTTP 404 with JSON-RPC error -32003 and `data.reason = "mcp_session_expired"`. Clients must re-initialize. The 60s floor prevents impractically short windows; the 86400s ceiling prevents idle sessions from accumulating indefinitely past the hard max-lifetime cap.

### `SACP_MCP_SESSION_MAX_LIFETIME_SECONDS`

- **Default**: `86400` (24 hours)
- **Type**: positive integer (seconds)
- **Valid range**: `600 <= value <= 604800` (inclusive — 10 minutes to 7 days)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_sacp_mcp_session_max_lifetime_seconds`
- **Source spec(s)**: 030 Phase 2 FR-034 (MCP session hard lifetime cap)
- **Note**: Hard cap enforced regardless of activity. Even a continuously active session is evicted after this many seconds from its `created_at`. Prevents indefinite accumulation of in-memory session state across long-running client connections. Server restart always evicts all sessions; this cap governs within-process accumulation.

### `SACP_MCP_MAX_CONCURRENT_SESSIONS`

- **Default**: `100`
- **Type**: positive integer
- **Valid range**: `1 <= value <= 10000` (inclusive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_sacp_mcp_max_concurrent_sessions`
- **Source spec(s)**: 030 Phase 2 FR-034 (MCP concurrent-session cap)
- **Note**: Per-instance in-memory cap. When the active session count reaches this value, subsequent `initialize` requests return HTTP 503 with a `Retry-After: 30` header (FR-027). Clients should back off and retry. Scale by increasing this value if the workload legitimately exceeds the default; note that each session consumes heap memory proportional to its metadata.

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
