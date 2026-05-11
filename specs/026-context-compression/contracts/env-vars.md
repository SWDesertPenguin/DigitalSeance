# Contract: Environment Variables (V16)

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec FR**: FR-025 | **Research**: [research.md §1, §2](../research.md)

Six env vars govern the compression stack. Four are new (introduced by this spec); two are already shipped via fix/* PRs and are documented here for completeness with rename-reconciliation notes per `research.md §2`.

## Naming reconciliation (rename direction: spec → code)

Two env vars named in the original spec text differ from the names that actually shipped via fix/* PRs:

| Spec 026 drafted name | Shipped name (source of truth) | Action |
|---|---|---|
| `SACP_CACHE_ANTHROPIC_TTL` | `SACP_ANTHROPIC_CACHE_TTL` | Keep shipped name. Update spec text at tasks-time. |
| `SACP_INFORMATION_DENSITY_THRESHOLD` | `SACP_DENSITY_ANOMALY_RATIO` | Keep shipped name. Update spec text at tasks-time. |

Operators searching either name find the correct doc section because `docs/env-vars.md` carries both names in a cross-reference header.

---

## `SACP_ANTHROPIC_CACHE_TTL` (existing — already shipped)

- **Purpose**: Anthropic prompt-cache TTL applied to cache_control breakpoints on Anthropic dispatches.
- **Type**: string enum.
- **Valid range**: `5m` | `1h`. Default `1h`.
- **Fail-closed semantics**: any value not in the enum exits at startup with a clear error naming the offending var.
- **Blast radius**: per-dispatch. Affects only Anthropic legs.
- **Anthropic context**: Anthropic dropped the default `1h` to `5m` silently in March 2026. Explicit configuration is the durable fix.

Validator: `validate_anthropic_cache_ttl` in `src/config/validators.py` (line 255). Registered in `VALIDATORS` tuple.

## `SACP_CACHING_ENABLED` (existing — already shipped)

- **Purpose**: master switch for provider-native caching (Layer 1).
- **Type**: boolean enum.
- **Valid range**: `0` | `1`. Default `1`.
- **Fail-closed semantics**: any value not in the enum exits at startup.
- **Blast radius**: process-wide. When `0`, all dispatches bypass Layer 1 caching directives.

Validator: `validate_caching_enabled` in `src/config/validators.py` (line 274). Registered in `VALIDATORS` tuple.

## `SACP_DENSITY_ANOMALY_RATIO` (existing — already shipped)

- **Purpose**: threshold ratio against the rolling baseline for the information-density signal (Layer 4 pre-compression signal per FR-018).
- **Type**: float.
- **Valid range**: `[1.0, 5.0]`. Default `1.5`.
- **Fail-closed semantics**: out-of-range or unparseable values exit at startup.
- **Blast radius**: per-turn density evaluation. Affects which turns get flagged via `convergence_log.tier='density_anomaly'` + the new `routing_log.reason='density_anomaly_flagged'` (Session 2026-05-11 §4 dual-write).

Validator: `validate_density_anomaly_ratio` in `src/config/validators.py` (line 279). Registered in `VALIDATORS` tuple.

---

## `SACP_CACHE_OPENAI_KEY_STRATEGY` (NEW)

- **Purpose**: routing strategy for OpenAI `prompt_cache_key`. `session_id` keeps a session's per-participant fan-out routed to the same backend for cache hit-rate; `participant_id` is available for operators who explicitly want per-participant cache partitioning.
- **Type**: string enum.
- **Valid range**: `session_id` | `participant_id`. Default `session_id`.
- **Fail-closed semantics**: any value not in the enum exits at startup.
- **Blast radius**: process-wide. Affects only OpenAI legs. Changing the value invalidates all existing OpenAI cache prefixes; operators should expect a one-cycle cache miss spike on flip.

Validator: NEW — `validate_cache_openai_key_strategy` in `src/config/validators.py`. Registered in `VALIDATORS` tuple at task time.

## `SACP_COMPRESSION_PHASE2_ENABLED` (NEW)

- **Purpose**: Phase 2 master switch. When `false` (default), Phase 2 compressors (`llmlingua2_mbert`, `selective_context`) raise `NotImplementedError` if dispatched. When `true`, the dispatch path can route to them per `SACP_COMPRESSION_DEFAULT_COMPRESSOR` or `sessions.compression_mode`.
- **Type**: boolean enum.
- **Valid range**: `true` | `false`. Default `false`.
- **Fail-closed semantics**: any value not in the enum exits at startup.
- **Blast radius**: process-wide. Affects all participants on all sessions. Flipping to `true` requires `transformers` + `accelerate` installed; absence causes a startup error from the LLMLingua2mBERTCompressor module.

Validator: NEW — `validate_compression_phase2_enabled` in `src/config/validators.py`. Registered at task time.

## `SACP_COMPRESSION_THRESHOLD_TOKENS` (NEW)

- **Purpose**: hard-compression engagement threshold. When the outgoing window's projected token count (per the target provider's TokenizerAdapter) exceeds this value, the dispatch path invokes the configured compressor instead of NoOp.
- **Type**: positive integer.
- **Valid range**: `[500, 100000]`. Default `4000` (literature default for LLMLingua-2 mBERT on English prose).
- **Fail-closed semantics**: out-of-range or unparseable values exit at startup. Below 500 makes compression overhead dominate any savings; above 100000 effectively disables compression for all real workloads.
- **Blast radius**: per-dispatch routing decision. Lowering raises compression invocation rate; raising lowers it.

Validator: NEW — `validate_compression_threshold_tokens` in `src/config/validators.py`. Registered at task time.

## `SACP_COMPRESSION_DEFAULT_COMPRESSOR` (NEW)

- **Purpose**: default compressor id used when `sessions.compression_mode='auto'`.
- **Type**: string from the registered compressor registry.
- **Valid range**: `noop` | `llmlingua2_mbert` | `selective_context`. Default `noop`.
- **Fail-closed semantics**: any value not in the registry exits at startup with an error listing the registered compressor names.
- **Blast radius**: process-wide. Flipping to a Phase 2 value requires `SACP_COMPRESSION_PHASE2_ENABLED=true` (else dispatches fail-closed per FR-020). The Phase 2 cutover is one env-var change per SC-007.

Validator: NEW — `validate_compression_default_compressor` in `src/config/validators.py`. Registered at task time. Validator MUST cross-check that the value is in the in-process `COMPRESSOR_IDS` set (`{noop, llmlingua2_mbert, selective_context, provence, layer6}`).

---

## V16 deliverable gate

Per FR-025 + Constitution V16, every env var named in this contract MUST have:

1. A validator function in `src/config/validators.py` registered in the `VALIDATORS` tuple.
2. A section in `docs/env-vars.md` carrying the six standard fields (Purpose, Type, Valid Range, Default, Fail-closed semantics, Blast radius).

The V16 CI gate (`scripts/check_env_vars.py`) flags any var read in `src/` but missing from `docs/env-vars.md`. The four new vars MUST pass the gate before `/speckit.tasks` advances. The two existing vars already pass; only the rename-cross-reference header needs to land.

## Cross-validator interaction

`SACP_COMPRESSION_PHASE2_ENABLED=true` AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop` is a valid-but-suspicious combination: Phase 2 is enabled but the default is NoOp. Emit a startup WARNING (NOT a `ValidationFailure`) naming the cross-var inconsistency.

`SACP_COMPRESSION_PHASE2_ENABLED=false` AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert` is a fail-closed combination: Phase 2 compressor is the default but Phase 2 is disabled. Startup MUST exit with a `ValidationFailure` naming both vars and the conflict.

`SACP_TOPOLOGY=7` AND `SACP_COMPRESSION_DEFAULT_COMPRESSOR != 'noop'` is a fail-closed combination: topology 7 supports Layer 1 caching only. Startup MUST exit with a `ValidationFailure` naming the topology incompatibility.
