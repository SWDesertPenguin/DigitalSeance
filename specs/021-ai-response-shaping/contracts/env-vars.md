# Contract: ai-response-shaping SACP_* env vars

Three new vars introduced in this feature. Each lands in `src/config/validators.py` AND `docs/env-vars.md` BEFORE `/speckit.tasks` per spec FR-014 (V16 deliverable gate).

## `SACP_FILLER_THRESHOLD`

- **Default**: unset (per-family default from `BehavioralProfile` dict in `src/orchestrator/shaping.py` applies — see [research.md §9](../research.md). Anthropic/openai default `0.60`; gemini/groq/ollama/vllm default `0.55`.)
- **Type**: float in `[0.0, 1.0]` inclusive
- **Valid range**: `0.0 <= value <= 1.0`. Values near `0.0` flag almost every draft; values near `1.0` flag almost nothing. When set, this env var overrides the per-family default uniformly across all six families.
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_filler_threshold`
- **Source spec(s)**: 021 §FR-002 / FR-003 / FR-004

## `SACP_REGISTER_DEFAULT`

- **Default**: `2` (Conversational) per spec §"Configuration (V16)" — matches observed default tone of Phase 1+2 sessions
- **Type**: integer in `[1, 5]`
- **Valid range**: `1` (Direct), `2` (Conversational), `3` (Balanced), `4` (Technical), `5` (Academic). Inclusive bounds.
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_register_default`
- **Source spec(s)**: 021 §FR-009 / FR-010 (initial session-row fallback when no `session_register` row exists)

## `SACP_RESPONSE_SHAPING_ENABLED`

- **Default**: `false` — the master switch ships off so deployments opt in explicitly. Per spec assumption: once SC-001's calibration target is validated against production traffic, the default may flip to `true` in a follow-up amendment.
- **Type**: boolean (string `"true"`/`"false"`, case-insensitive; integer `"1"`/`"0"` accepted per existing validator convention)
- **Valid range**: exactly `true` or `false` (after case-folding)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_response_shaping_enabled`
- **Source spec(s)**: 021 §FR-005 / SC-002

**Note**: Setting this var to `false` MUST disable the entire filler-scorer + retry pipeline; pre-feature acceptance tests MUST pass byte-identically (SC-002 regression contract). The register slider is independent of this switch — slider deltas always emit regardless of master-switch state, since the slider is a prompt-composition concern not a shaping concern (spec edge case).

## CI-gate alignment

Per spec 012 FR-005 the `scripts/check_env_vars.py` gate scans `src/` for `os.environ.get("SACP_*")` calls and asserts each has a section in `docs/env-vars.md`. The three vars above MUST satisfy that gate before `/speckit.tasks` is run for this spec.

The validators MUST also be appended to the `VALIDATORS` tuple in `src/config/validators.py` so they fire during `validate_all()` at orchestrator startup (V16 contract).

No cross-validator dependencies among the three vars — each is independently validated. (Contrast with spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` cross-validator pair.)
