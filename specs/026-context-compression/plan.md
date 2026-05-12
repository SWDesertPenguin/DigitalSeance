# Implementation Plan: Context Compression and Distillation (Six-Layer Stack)

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/026-context-compression/spec.md`

## Summary

Spec 026 ships the six-layer context-compression and distillation envelope under one constitutional umbrella. The work is multi-phase and partly already in tree via `fix/*` PRs — Layer 1 (provider-native caching) lives at [src/api_bridge/caching.py](../../src/api_bridge/caching.py), the TokenizerAdapter interface lives at [src/api_bridge/tokenizer.py](../../src/api_bridge/tokenizer.py), and the information-density signal lives at [src/orchestrator/density.py](../../src/orchestrator/density.py); the V16 validators `SACP_ANTHROPIC_CACHE_TTL`, `SACP_CACHING_ENABLED`, and `SACP_DENSITY_ANOMALY_RATIO` are already registered in [src/config/validators.py](../../src/config/validators.py). Spec 026 (a) formalises those landings under a constitutional spec, (b) reconciles the spec's drafted env-var names with the names that actually shipped (see `research.md §2`), (c) introduces the `compression_log` table and `sessions.compression_mode` column with a forward-only alembic migration, (d) defines the `CompressorService` registry interface + the `NoOpCompressor` Phase 1 default that writes a `compression_log` row on every dispatch, (e) scaffolds the Phase 2 `LLMLingua2mBERTCompressor` + `SelectiveContextCompressor` and Phase 3 `NoOpProvenceAdapter` + `NoOpLayer6Adapter` as stubs that fail-closed at the registry boundary until their respective gates open, (f) wires the routing_log `reason` enum to carry the four new compression markers (`cache_hit`, `cache_miss`, `compression_applied`, `compression_pipeline_error`, `density_anomaly_flagged`) per Session 2026-05-11 §4 dual-write, (g) ships the summarizer-corpus filter for density-flagged turns (FR-019) — the one new behavioural change Phase 1 contributes beyond formalisation, and (h) lands the architectural tests that prevent direct compressor imports and direct convergence-detector compression reads (FR-023 + FR-024). Phase 2 and Phase 3 stay scaffold-only behind their env-var gates until operators opt in.

Technical approach: extend `src/config/validators.py` with the four new env vars and align the two existing ones to the spec text (rename the spec text, NOT the validators — code is the source of truth, see `research.md §2`); introduce `src/compression/` package with `service.py` (CompressorService registry), `noop.py` (NoOpCompressor), `llmlingua2_mbert.py` (Phase 2 default scaffold), `selective_context.py` (Phase 2 fallback scaffold), `provence.py` (Phase 3 scaffold), `layer6.py` (Phase 3 scaffold), `markers.py` (XML boundary marker assembly), and `trust_tier.py` (MIN-tier inheritance per Session 2026-05-11 §3); introduce `src/repositories/compression_repo.py` for `compression_log` INSERTs; ship one alembic migration adding `compression_log` table + `sessions.compression_mode` column and mirror the schema in `tests/conftest.py` per `feedback_test_schema_mirror`; add `density_anomaly_flagged` to the routing_log reason enum and wire the per-turn dual-write at the existing density-signal call site in `src/orchestrator/density.py`; add the summarizer-corpus filter for density-flagged turns at the summarizer call site in `src/orchestrator/summarization.py` (or wherever spec 005 lands the summarizer); wire the bridge layer to call `CompressorService.compress(...)` on every dispatch (NoOp returns input verbatim — byte-identical to today's dispatch — but writes the telemetry row); land the four `reason` strings into the spec 003 §FR-030 enumeration; wire architectural tests asserting compressor-package boundary and raw-transcript convergence read. No new third-party Python dependencies for Phase 1 — LLMLingua-2 mBERT lands `transformers` + `accelerate` only when Phase 2 is enabled (gated). Frontend: zero new modules; no SPA surface for Phase 1 (admin metrics panel for cache hit rate + compression ratio + density baseline is a coordinated spec 011 amendment FR set, drafted for tasks-time per `reminder_spec_011_amendments_at_impl_time`).

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm).
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. **No new backend runtime dependencies for Phase 1.** Phase 2's LLMLingua-2 mBERT lands `transformers` (the Hugging Face library) + `accelerate` behind `SACP_COMPRESSION_PHASE2_ENABLED=true` — these are deferred to the Phase 2 task list, NOT this PR's deliverables. Existing dependencies in scope: `tiktoken` (already in tree via the tokenizer adapter), `sentence-transformers` (already loaded for spec 004 convergence). Frontend: no new third-party libraries.
**Storage**: PostgreSQL 16. **One new table** (`compression_log`) and **one new column** (`sessions.compression_mode`). One new alembic migration ships at task time; schema mirrored in `tests/conftest.py` per `feedback_test_schema_mirror`. Migration revision pre-allocated as `018` (assumes spec 022's `017_detection_events.py` lands first; if 026 ships before 022, swap to `017` and renumber 022 — coordination per `feedback_parallel_merge_sequence_collisions`). Compression_log is append-only per spec 001 §FR-008; forward-only migration per §FR-017.
**Testing**: pytest with the existing per-test FastAPI fixture (spec 012 US7). DB-gated tests follow the `tests/conftest.py` schema-mirror pattern; pure-logic compressor tests run without DB. Phase 2 LLMLingua-2 tests skip in CI unless `transformers` is installed (marker: `@pytest.mark.requires_phase2`). Architectural tests in `tests/test_026_architectural.py` cover FR-023/FR-024 (compressor boundary + raw-transcript convergence). Quickstart smoke test runs against a live orchestrator with the master switch toggled.
**Target Platform**: Linux server (Docker Compose, Debian slim-bookworm).
**Project Type**: Web service (single project; existing `src/` + `frontend/` + `tests/` layout).
**Performance Goals**:
- Layer 1 (caching): zero orchestrator-side compute; gain is provider-side TTFT reduction (Anthropic up to ~85%, OpenAI up to ~80% on second-turn hits per provider documentation). Budget enforcement: cache-hit / cache-miss markers in `routing_log` plus structured-log emission for external dashboards.
- Layer 4 (LLMLingua-2 mBERT, Phase 2): ~200ms per 1K tokens on CPU; breakeven threshold ~4K tokens. Budget enforcement: `compression_log.duration_ms` per-call timing.
- CompressorService dispatch overhead: O(1) virtual method dispatch; the abstraction MUST NOT introduce buffering, copying, or serialization beyond what the compressor already does. Budget enforcement: per-dispatch timing comparison against the un-compressor-mediated baseline (asserted in `tests/test_026_perf_budgets.py`).
- Information-density signal: zero additional cost; reuses spec 004's sentence-transformers infrastructure. Budget enforcement: per-turn `routing_log.shaping_score_ms` inclusive of density evaluation.
**Constraints**:
- Phase 2 stays scaffold-only until `SACP_COMPRESSION_PHASE2_ENABLED=true`. Phase 3 layers stay scaffold-only until their respective gating specs ship (retrieval surface for Layer 5; local-model-support for Layer 6).
- Default behaviour MUST be unchanged in Phase 1: NoOpCompressor is byte-identical to un-compressor-mediated dispatch (SC-006), and `compression_log` writes do not block dispatch on failure (FR-020).
- §V15 fail-closed: invalid env-var values exit at startup (V16); compression failures fall through to un-compressed dispatch + structured-log error (FR-020).
- 25/5 coding standards (Constitution §6.10) + 25-line function cap.
- §4.13 [PROVISIONAL] inter-AI shorthand: spec 026 explicitly rejects negotiated inter-AI shorthand in the "Out of Scope" list. Clears the rule by construction.
- §4.10 / V17 transcript canonicity: per-participant pre-bridge placement (FR-010) ensures compression artefacts NEVER replace the canonical transcript. The convergence detector + adversarial rotation read the raw transcript via the message-store interface (FR-013, architectural test FR-024). Compression operates only on a participant's outgoing window; the message store is untouched.
- §7 derived-artifact traceability / V18: every compressed segment carries an XML boundary marker recording the compressor id + version + trust tier (FR-012). Reviewers can walk from the marker back to the canonical source via the `compression_log` row, which records source_tokens + output_tokens + compressor_id + compressor_version.
**Scale/Scope**: Phase 3 ceiling of 5 participants per session. Per-turn compression invocations are 1-per-participant-per-turn (≤ 5 per turn). NoOpCompressor invocations are unconditional (every dispatch writes one `compression_log` row); table growth at the Phase 3 ceiling is bounded by `dispatches_per_session × sessions_per_day`. The `compression_log` table is append-only and retention-capped via `SACP_LOG_RETENTION_DAYS` (existing spec 010 retention surface; no new retention env var introduced by 026).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Note |
|---|---|---|
| **V1 Sovereignty** | PASS | Compression is internal to the bridge layer. No participant API key, model choice, or budget is exposed. Per-participant pre-bridge placement (FR-010) preserves the existing sovereignty boundary — one participant's compressed view never reaches another. |
| **V2 No cross-phase leakage** | PASS | Spec is multi-phase. Phase 1 is partially shipped via fix/* + formalised here. Phase 2 + Phase 3 stay scaffold-only behind env-var gates. No Phase 4 capabilities required. |
| **V3 Security hierarchy** | PASS | Compressor operates strictly downstream of the spec 007 sanitize / spotlight / output-validate pipeline (compression is post-validation, pre-dispatch on the OUTGOING context). The convergence detector + adversarial rotation read the raw transcript, NOT the compressed view (FR-013, FR-024). |
| **V4 Facilitator powers bounded** | PASS | Compression is operator-configured via env vars + `sessions.compression_mode`; no participant-side configurability. Facilitator can force a specific layer via `sessions.compression_mode='<layer>'` but cannot bypass the trust-tier envelope or the priority-tier-1 protection. |
| **V5 Transparency** | PASS | Every dispatch writes a `compression_log` row (FR-007, SC-013). Routing log carries `cache_hit` / `cache_miss` / `compression_applied` / `compression_pipeline_error` / `density_anomaly_flagged` markers. The compression envelope is fully traceable. |
| **V6 Graceful degradation** | PASS | Compression failure falls through to un-compressed dispatch (FR-020). NoOpCompressor is byte-identical to un-compressor-mediated dispatch (SC-006). Phase 2 scaffold registers but is opt-in via env var; Phase 3 scaffolds register as no-ops on closed-API legs (FR-022, SC-011). |
| **V7 Coding standards** | PASS | Function bodies stay under 25 lines; compressor classes split per-layer to keep each implementation focused. The 5-arg positional limit holds for the `compress(payload, target_budget, trust_tier)` signature (3 args). |
| **V8 Data security** | PASS | Compression operates per-participant pre-bridge (FR-010); cross-participant cache contamination is structurally impossible (FR-004 cache-key tuple includes `participant_id`). Compressed segments inherit source trust tier (FR-011 + Session 2026-05-11 §3 MIN-tier resolution) so downstream consumers see a conservative envelope on mixed-tier inputs. |
| **V9 Log integrity** | PASS | `compression_log` is append-only per spec 001 §FR-008. The application DB role has INSERT/SELECT only (no UPDATE/DELETE) per Constitution §6.2. Migration is forward-only per §FR-017. |
| **V10 AI security pipeline** | PASS | Compressed segments inherit source trust tier (FR-011); XML boundary markers (FR-012) signal compressed regions to any downstream check. Priority-tier-1 content (system prompt + tool defs) is NEVER compressed (FR-014); the compressor refuses to operate on tier-1 input. The convergence detector + adversarial rotation read the raw transcript (FR-013) so compression artefacts can never bypass the spec 007 pipeline. |
| **V11 Supply chain** | PASS-ON-DELIVERY | Phase 1 introduces no new dependencies. Phase 2 will require `transformers` + `accelerate` when LLMLingua-2 mBERT is enabled; those land at Phase 2 task time with the standard hash-lock per Constitution §6.3. |
| **V12 Topology compatibility** | PASS | Spec §"Topology and Use Case Coverage (V12/V13)" enumerates: Layers 1-4 apply to topologies 1-6 (orchestrator-driven); Layer 5 applies if a retrieval surface is configured; Layer 6 applies only to legs running open-weight models; Topology 7 uses Layer 1 only via per-MCP-client provider settings. Topology gate at module-mount per `research.md §5`. |
| **V13 Use case coverage** | PASS | Spec §V13 maps to all use cases §1-§7. Layer 1 caching benefits all; Layer 2 structural deduplication benefits all; Layer 4 hard compression benefits §2 (research co-authorship) and §5 (technical review) most once Phase 2 enables long-history sessions. |
| **V14 Performance budgets** | PASS | Four budgets specified in spec §"Performance Budgets (V14)" + `research.md §14`: Layer 1 (cache hit/miss markers), Layer 4 (`compression_log.duration_ms`), CompressorService dispatch overhead (vs un-compressor-mediated baseline), information-density signal (reuses spec 021 §FR-011 timing). Architectural test enforces baseline parity in `tests/test_026_perf_budgets.py`. |
| **V15 Fail-closed** | PASS | Invalid env-var values exit at startup (V16). Compression failures fall through to un-compressed dispatch with structured-log error (FR-020) — fail-soft on the dispatch path while preserving fail-closed at config-load time. The two failure modes target different surfaces. |
| **V16 Configuration validated at startup** | PASS-ON-DELIVERY | Four new env vars require validators + `docs/env-vars.md` sections (V16 deliverable gate per FR-025). Two existing env vars (`SACP_ANTHROPIC_CACHE_TTL`, `SACP_DENSITY_ANOMALY_RATIO`) are already registered; spec text rename happens at tasks-time, code is source of truth. Validators land in this feature's task list. |
| **V17 Transcript canonicity respected** | PASS | Compression operates on a participant's outgoing context window only. The message store (canonical transcript) is untouched. Convergence detector + adversarial rotation read the message store, NOT the bridge view (FR-013, FR-024). |
| **V18 Derived artifacts traceable** | PASS | Every compressed segment carries the XML boundary marker (FR-012) with compressor id + version + trust tier. The `compression_log` row records source_tokens + output_tokens + compressor_id + compressor_version + duration_ms per dispatch. Reviewers walk from boundary marker back to the canonical pre-compression source via the row. |
| **V19 Evidence and judgment markers** | PASS | Spec uses [JUDGMENT] / drafted-as / [NEEDS CLARIFICATION] markers consistently. Session 2026-05-11 resolved the four [NEEDS CLARIFICATION] markers; empirical-default calibration items remain Phase-1-traffic-gated per the original framing. Historical draft positions retained for traceability. |

No violations. Complexity Tracking section below remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/026-context-compression/
├── plan.md                              # This file (/speckit.plan command output)
├── research.md                          # Phase 0 output — 16 sections covering existing-surface audit + new-surface design
├── data-model.md                        # Phase 1 output — compression_log + sessions.compression_mode + CompressedSegment + registry
├── quickstart.md                        # Phase 1 output — end-to-end smoke for cache hit/miss + NoOp dispatch + density filter + Phase 2 enable
├── contracts/                           # Phase 1 output
│   ├── env-vars.md                      # 6 env vars (4 new + 2 existing + rename reconciliation)
│   ├── compressor-service-interface.md  # CompressorService registry shape; compress(payload, target_budget, trust_tier) -> CompressedSegment contract
│   ├── compression-log-row.md           # compression_log column shape + per-dispatch invariants + NoOp row shape
│   └── routing-log-additions.md         # routing_log.reason enum additions (cache_hit / cache_miss / compression_applied / compression_pipeline_error / density_anomaly_flagged)
├── spec.md                              # Feature spec (Status: Clarified 2026-05-11)
└── tasks.md                             # Phase 2 output (/speckit.tasks command — NOT created here)
```

### Source Code (repository root)

```text
src/
├── api_bridge/
│   ├── caching.py                       # REUSE — Layer 1 caching directives (already shipped via fix/api-bridge-caching); add cache_hit/cache_miss routing_log emission at the LiteLLM response-handling site
│   ├── tokenizer.py                     # REUSE — TokenizerAdapter (already shipped via fix/api-bridge-tokenizer-adapter); spec 026 documents the integration boundary
│   └── adapter.py                       # REUSE — spec 020 ProviderAdapter ABC; cache-control normalisation lands here per spec 020 FR-010
├── compression/                         # NEW PACKAGE
│   ├── __init__.py                      # NEW — package docstring referencing spec 026; exports CompressorService, NoOpCompressor, CompressedSegment
│   ├── service.py                       # NEW — CompressorService process-scope registry; register(compressor_id, compressor_class); compress(...) dispatch; read-only after startup
│   ├── noop.py                          # NEW — NoOpCompressor; pass-through; writes compression_log row per Session 2026-05-11 §2
│   ├── llmlingua2_mbert.py              # NEW (scaffold) — LLMLingua2mBERTCompressor; raises NotImplementedError until Phase 2 enabled
│   ├── selective_context.py             # NEW (scaffold) — SelectiveContextCompressor; Phase 2 fallback; same NotImplementedError pattern
│   ├── provence.py                      # NEW (scaffold) — NoOpProvenceAdapter; Layer 5 stub per FR-021
│   ├── layer6.py                        # NEW (scaffold) — NoOpLayer6Adapter; Layer 6 stub per FR-022 + closed-API-leg skip
│   ├── markers.py                       # NEW — XML boundary marker assembly; wrap(text, source_tier, compressor_id, version) -> str
│   ├── trust_tier.py                    # NEW — MIN-tier inheritance per Session 2026-05-11 §3; tier_1_refuse(...) enforcement for FR-014
│   └── segments.py                      # NEW — CompressedSegment dataclass; output_tokens, output_text, trust_tier, boundary_marker, compressor_id, compressor_version
├── orchestrator/
│   ├── density.py                       # REUSE — density signal (already shipped via fix/quality-density-signal); add routing_log dual-write per Session 2026-05-11 §4
│   ├── summarization.py                 # extend — filter density-flagged turns from summarizer corpus per FR-019 (new Phase 1 behavioural change)
│   └── loop.py                          # extend — wire CompressorService.compress(...) at the per-participant pre-bridge dispatch site
├── repositories/
│   ├── compression_repo.py              # NEW — insert_compression_log(row); read helpers for telemetry queries
│   └── log_repo.py                      # extend — routing_log.reason enum addition emit helpers for the four new markers
├── config/
│   └── validators.py                    # extend — 4 new validators (SACP_CACHE_OPENAI_KEY_STRATEGY, SACP_COMPRESSION_PHASE2_ENABLED, SACP_COMPRESSION_THRESHOLD_TOKENS, SACP_COMPRESSION_DEFAULT_COMPRESSOR); existing SACP_ANTHROPIC_CACHE_TTL + SACP_DENSITY_ANOMALY_RATIO unchanged

alembic/versions/
└── 018_compression_log.py               # NEW — compression_log table + sessions.compression_mode column; forward-only per spec 001 §FR-017

tests/
├── test_026_validators.py               # NEW — 4 new env-var validators
├── test_026_compressor_service.py       # NEW — registry shape, register/get, read-only-after-startup, unregistered key error
├── test_026_noop_compressor.py          # NEW — pass-through invariant (SC-006 byte-identical), compression_log row writes (SC-013)
├── test_026_compression_log.py          # NEW — table shape, append-only invariant, NoOp + Phase 2 row shapes
├── test_026_density_dual_write.py       # NEW — Session 2026-05-11 §4 dual-write; convergence_log + routing_log emission in same per-turn transaction
├── test_026_summarizer_filter.py        # NEW — FR-019 density-flagged turn filter on summarizer corpus (new Phase 1 behavioural change)
├── test_026_markers_trust_tier.py       # NEW — XML boundary marker assembly + MIN-tier inheritance + tier-1 refusal
├── test_026_architectural.py            # NEW — FR-023 compressor-package import boundary, FR-024 raw-transcript convergence read
├── test_026_routing_log_markers.py      # NEW — 5 new reason values emit at the right call sites
├── test_026_phase2_scaffold.py          # NEW — LLMLingua2mBERTCompressor + SelectiveContextCompressor raise NotImplementedError until SACP_COMPRESSION_PHASE2_ENABLED=true
├── test_026_phase3_scaffolds.py         # NEW — NoOpProvenceAdapter + NoOpLayer6Adapter register without error; Layer 6 skipped on closed-API legs
├── test_026_perf_budgets.py             # NEW — V14 budget enforcement; NoOp dispatch overhead vs baseline
├── test_026_master_switch_phase2.py     # NEW — SACP_COMPRESSION_PHASE2_ENABLED=false leaves the registry default at NoOp
└── test_026_quickstart_seed.py          # NEW — fixture for the quickstart smoke test

docs/
└── env-vars.md                          # extend — add 4 new sections (V16 gate per FR-025); the 2 existing sections need a header note about the rename reconciliation
```

**Structure Decision**: Single Python service ("Option 1") consistent with the existing repo layout. The compressor package factors out under `src/compression/` so the dispatch path imports `from src.compression.service import CompressorService` and never reaches concrete compressor implementations directly (FR-023 architectural test). Phase 2 + Phase 3 scaffolds live in the same package so the registry exposes them uniformly; the env-var gates control behavioural activation, not module presence. Existing modules (`src/api_bridge/caching.py`, `src/api_bridge/tokenizer.py`, `src/orchestrator/density.py`) are NOT moved — they retain their current locations and spec 026 documents the integration boundary in `research.md §1` rather than refactoring.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Section intentionally empty.

## Notes for /speckit.tasks

Anchor list of tasks (cross-referenced from `research.md` and the spec):

- V16 gate first: T001-T0XX add the 4 new env-var validators + 4 new `docs/env-vars.md` sections + the 2 existing-section rename notes BEFORE any other Phase 1 task lands.
- Schema migration second: alembic 018 with `tests/conftest.py` schema mirror. The compression_log table + sessions.compression_mode column ship together.
- Master-switch-off canary lands BEFORE any compression call-site sweep: a test that confirms `SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop` (default) preserves byte-identical-to-baseline dispatch behaviour.
- Architectural tests (FR-023 + FR-024) land in Phase 2 (foundational) — they enforce the compressor-package boundary that the rest of the work depends on. Adding architectural tests AFTER call-site sweeps would invite regressions.
- Spec 011 amendment FR set drafted at tasks-time per `reminder_spec_011_amendments_at_impl_time.md` — admin metrics panel surfaces cache hit rate + compression ratio + density baseline.
