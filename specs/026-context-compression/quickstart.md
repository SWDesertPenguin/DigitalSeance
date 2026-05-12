# Quickstart: Context Compression and Distillation

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

End-to-end smoke test for Phase 1 of the compression stack. Runs against a live orchestrator. Validates US1 (provider-native caching), US2 (information-density signal + dual-write), US3 (NoOpCompressor + log-on-noop invariant), and Phase 2 toggle behaviour.

## Prerequisites

- Local stack running per `docs/deployment.md`: `docker compose up` brings up Postgres + orchestrator + Web UI on ports 5432/8000.
- A facilitator account authenticated in a browser tab at `http://localhost:8000`.
- At least one closed-API provider configured (Anthropic, OpenAI, or Gemini) — the cache-hit / cache-miss markers fire only on closed-API legs.
- Env vars set (defaults work for steps 1-6):
  - `SACP_CACHING_ENABLED=1` (default)
  - `SACP_ANTHROPIC_CACHE_TTL=1h` (default)
  - `SACP_CACHE_OPENAI_KEY_STRATEGY=session_id` (default)
  - `SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop` (default)
  - `SACP_COMPRESSION_PHASE2_ENABLED=false` (default)
  - `SACP_COMPRESSION_THRESHOLD_TOKENS=4000` (default)
  - `SACP_DENSITY_ANOMALY_RATIO=1.5` (default)

## Step 1 — Open a session and dispatch a first turn

1. From the facilitator dashboard, click "New session" with 1 AI participant on Anthropic + 1 human (facilitator). Mode: any.
2. Send a turn ("Hello, can you summarise the topic?"). Wait for the AI response.
3. **Expected**:
   - One routing_log row with `reason='cache_miss'` (first turn — no prior cache).
   - One compression_log row with `compressor_id='noop'`, `output_tokens == source_tokens`, `duration_ms < 1`.
   - Dispatch payload is byte-identical to un-compressor-mediated baseline (SC-006).

## Step 2 — Second turn: verify cache_hit on Anthropic

1. Send a second turn ("And what about the implications?"). Wait for the response.
2. **Expected**:
   - One routing_log row with `reason='cache_hit'` + `cached_prefix_tokens=<N>` (the prefix from turn 1 is cached on Anthropic's side).
   - One compression_log row with `compressor_id='noop'`.
   - Provider-side TTFT reduction visible in the response timing (typically ~85% reduction on Anthropic per provider docs).

## Step 3 — Force a density anomaly: verify dual-write

1. Configure the AI participant with a verbose prompt: `"please respond with at least 500 words to any question, repeating yourself as needed"`.
2. Send a turn that elicits a verbose low-content response.
3. **Expected** (Session 2026-05-11 §4 dual-write):
   - One convergence_log row with `tier='density_anomaly'` and `target_event_id=<turn_id>` (existing spec 004 path).
   - One routing_log row with `reason='density_anomaly_flagged'` + `density_value=<X>` + `baseline_mean=<Y>` + `ratio=<X/Y>`.
   - Both writes share the same transaction; either both commit or neither does.
4. Query the orchestrator log: `SELECT count(*) FROM routing_log WHERE reason='density_anomaly_flagged' AND session_id=<sess>` — should be ≥ 1.

## Step 4 — Force the summarizer to filter the flagged turn (FR-019 — Phase 1 behavioural change)

1. From Step 3, you have at least one density-flagged turn. Drive the session to N turns where N exceeds the summarizer's rolling-summary threshold (typically 10 turns per spec 005 default).
2. Wait for the summarizer to fire.
3. **Expected**: the rolling-summary output does NOT contain content from the flagged turn. The summarizer filters density-flagged turns from the corpus per FR-019.
4. Verify in the database: `SELECT summary_content FROM convergence_log WHERE tier='summary_checkpoint' AND session_id=<sess>` — the resulting summary text should not contain phrasing characteristic of the flagged turn's verbose output.

## Step 5 — Try to enable a Phase 2 compressor without Phase 2 flag

1. Stop the orchestrator. Set `SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert` BUT leave `SACP_COMPRESSION_PHASE2_ENABLED=false`. Restart.
2. **Expected**: the orchestrator MUST exit at startup with a `ValidationFailure` naming both env vars and the cross-validator incompatibility (per `contracts/env-vars.md` cross-validator section).

## Step 6 — Enable Phase 2 scaffold; verify it raises NotImplementedError

1. Set `SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert` AND `SACP_COMPRESSION_PHASE2_ENABLED=true`. Start the orchestrator.
2. Send a turn that exceeds `SACP_COMPRESSION_THRESHOLD_TOKENS=4000` (paste a long system prompt or accumulate history).
3. **Expected** (Phase 1 ships LLMLingua-2 mBERT as scaffold-only):
   - The compressor raises `NotImplementedError` per `research.md §8`.
   - The CompressorService catches the exception and emits `routing_log.reason='compression_pipeline_error'` with `compressor_id='llmlingua2_mbert'` and `error_class='NotImplementedError'`.
   - The dispatch falls through to un-compressed payload per FR-020 — the turn completes successfully despite the compressor failure.

## Step 7 — Force a session into `compression_mode='off'`

1. Stop. Restore `SACP_COMPRESSION_DEFAULT_COMPRESSOR=noop`, `SACP_COMPRESSION_PHASE2_ENABLED=false`. Start.
2. Via psql or the spec 010 admin tools, UPDATE a specific session's row: `UPDATE sessions SET compression_mode='off' WHERE id='<session_id>'`.
3. Send a turn on that session.
4. **Expected**:
   - One compression_log row with `compressor_id='noop'` (off resolves to noop per `data-model.md`).
   - Dispatch payload byte-identical to baseline (SC-006).

## Step 8 — Verify Layer 6 skip on closed-API legs (SC-011)

1. Stop. Set `SACP_COMPRESSION_DEFAULT_COMPRESSOR=layer6` AND `SACP_COMPRESSION_PHASE2_ENABLED=true`. Start.
2. Send a turn to the Anthropic participant (closed-API leg).
3. **Expected**:
   - `NoOpLayer6Adapter.supports('anthropic')` returns False.
   - The dispatch path skips Layer 6 entirely without error.
   - The compression_log row carries `compressor_id='noop'` (fallback to NoOp on Layer 6 skip).
   - No `compression_pipeline_error` routing_log marker — the skip is by design, not a failure (FR-022 + SC-011).

## Step 9 — Verify topology 7 mount gate

1. Stop. Set `SACP_TOPOLOGY=7`, `SACP_COMPRESSION_DEFAULT_COMPRESSOR=llmlingua2_mbert`. Start.
2. **Expected**: orchestrator exits at startup with a ValidationFailure naming the topology-7 incompatibility per `research.md §5` + `contracts/env-vars.md` cross-validator section.

## Step 10 — Verify the architectural test boundary (FR-023)

1. Run `pytest tests/test_026_architectural.py -v`.
2. **Expected**: all tests pass:
   - `test_no_direct_compressor_imports_outside_compression_package` — confirms no file under `src/` outside `src/compression/` imports a concrete compressor.
   - `test_convergence_detector_reads_raw_transcript_not_bridge_view` — confirms the convergence-detector code path reads via the message-store interface, NOT the compressed bridge view.

## Pass criteria

Steps 1-10 complete with expected results. Step 6's "NotImplementedError caught and falls through" behaviour is the key Phase 2 scaffold validation; step 3-4's dual-write + summarizer filter is the key Phase 1 behavioural delta. Any deviation gets captured as a follow-up ticket on this branch before merge.

## Cleanup

```bash
# Reset env vars to defaults; restart orchestrator.
unset SACP_COMPRESSION_DEFAULT_COMPRESSOR
unset SACP_COMPRESSION_PHASE2_ENABLED
unset SACP_TOPOLOGY
docker compose restart orchestrator
```

Any sessions created during the smoke test can stay; the per-session `compression_mode` column has no schema-side cleanup obligation (append-only data model).
