# Contract: `compression_log` Row Shape

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec FR**: FR-005, FR-007 | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md §3, §6](../research.md)

Per-dispatch telemetry row. One row per `CompressorService.compress(...)` invocation, INCLUDING NoOp dispatches per Session 2026-05-11 §2 + SC-013.

## Row shape

| Column | Type | Required | Notes |
|---|---|---|---|
| `id` | bigserial | auto | Primary key. |
| `session_id` | text | yes | The session id. |
| `turn_id` | text | yes | The turn id within the session. Joins to `routing_log.turn_id`. |
| `participant_id` | text | yes | The participant whose outgoing window this dispatch targets. |
| `source_tokens` | integer | yes | Token count before compression (from target provider's TokenizerAdapter). |
| `output_tokens` | integer | yes | Token count after compression. NoOp: equal to `source_tokens`. |
| `compressor_id` | text | yes | One of `noop`, `llmlingua2_mbert`, `selective_context`, `provence`, `layer6`. CHECK constrained. |
| `compressor_version` | text | yes | Compressor's `COMPRESSOR_VERSION` class attribute. |
| `trust_tier` | text | yes | One of `system`, `facilitator`, `participant_supplied`. CHECK constrained. Resolved MIN-tier per Session 2026-05-11 §3 (NoOp: passes input tier verbatim). |
| `layer` | text | yes | Layer name (1:1 with `compressor_id` for the registered compressors). Kept for clearer cross-spec joins. |
| `duration_ms` | real | yes | Wall-clock timing of the compressor body via `time.perf_counter()`. |
| `created_at` | timestamptz | auto | DEFAULT NOW(). |

## NoOp row example

```sql
INSERT INTO compression_log
  (session_id, turn_id, participant_id, source_tokens, output_tokens,
   compressor_id, compressor_version, trust_tier, layer, duration_ms)
VALUES
  ('sess_abc', 'turn_42', 'pp_alice', 387, 387,
   'noop', '1', 'participant_supplied', 'noop', 0.31);
```

`output_tokens == source_tokens` is the NoOp invariant; the dispatch is byte-identical to un-compressor-mediated dispatch per SC-006.

## Phase 2 row example (LLMLingua-2 mBERT)

```sql
INSERT INTO compression_log
  (session_id, turn_id, participant_id, source_tokens, output_tokens,
   compressor_id, compressor_version, trust_tier, layer, duration_ms)
VALUES
  ('sess_abc', 'turn_99', 'pp_alice', 6432, 1873,
   'llmlingua2_mbert', '1', 'participant_supplied', 'llmlingua2_mbert', 1289.5);
```

`output_tokens < source_tokens` reflects the compression ratio. `duration_ms` records the compressor body timing.

## Invariants

1. **Append-only** (spec 001 §FR-008): no UPDATE or DELETE permitted. Application DB role has INSERT/SELECT only per Constitution §6.2.
2. **One row per dispatch** (SC-013): every `CompressorService.compress(...)` call writes exactly one row, including NoOp dispatches.
3. **Non-negative numerics**: `source_tokens >= 0`, `output_tokens >= 0`, `duration_ms >= 0`. CHECK constraints enforce.
4. **Enum constraints**: `compressor_id` in the registered set; `trust_tier` in the three-value set.
5. **Forward-only migration** (spec 001 §FR-017): alembic `018_compression_log.py` downgrade is a no-op.

## Read patterns

- **Per-session telemetry**: `SELECT ... FROM compression_log WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2`. Index `compression_log_session_created_idx` supports.
- **Per-layer metrics** (spec 016 metrics surface): `SELECT compressor_id, AVG(output_tokens::float / NULLIF(source_tokens, 0)) FROM compression_log WHERE created_at > $1 GROUP BY compressor_id`. Index `compression_log_compressor_created_idx` supports.
- **Phase 2 cutover analysis**: compare `output_tokens / source_tokens` ratios across `compressor_id` before/after cutover to validate the compression gain.

## Retention

Append-only with retention via the existing `SACP_LOG_RETENTION_DAYS` envelope (spec 010 §FR-005). Spec 026 does NOT introduce a new retention env var. Deletion runs through the existing log-retention sweep job.

## V18 traceability

`compression_log` row + XML boundary marker on the dispatched segment together encode the derivation method:

1. Reviewer sees a `<compressed>` segment in a dispatched window.
2. Marker carries `compressor` + `version` + `source-tier`.
3. Query `compression_log WHERE turn_id = <X> AND participant_id = <Y> AND compressor_id = <Z>` to find the canonical telemetry row.
4. Row encodes `source_tokens` (pre-compression) and `output_tokens` (post-compression) — the size delta IS the compression effect.

The class-mapping registry IS the derivation method; the per-dispatch row IS the per-dispatch evidence.
