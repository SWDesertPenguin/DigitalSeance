# Contract: `CompressorService` Interface

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec FR**: FR-006, FR-007, FR-010, FR-011, FR-012, FR-014, FR-020, FR-023 | **Data model**: [data-model.md](../data-model.md) | **Research**: [research.md §5, §6, §7](../research.md)

## Module

`src/compression/service.py`

## Public API

```python
class CompressorService:
    def register(self, compressor_id: str, compressor_class: type[Compressor]) -> None: ...
    def freeze(self) -> None: ...
    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
        *,
        compressor_id: str | None = None,
        session_id: str,
        participant_id: str,
        turn_id: str,
    ) -> CompressedSegment: ...
```

## `register(compressor_id, compressor_class)`

Adds a compressor class to the registry. MUST be called at module import time. Calling after `freeze()` raises `RuntimeError`.

**Idempotency**: re-registering the same `compressor_id` raises `ValueError`. The registry has no replace semantics — replacement requires process restart.

## `freeze()`

Marks the registry as read-only. Called once at FastAPI lifespan startup, AFTER all compressor modules have imported and registered. Subsequent `register()` calls raise `RuntimeError`.

## `compress(payload, target_budget, trust_tier, *, compressor_id, session_id, participant_id, turn_id) -> CompressedSegment`

Dispatches to the configured compressor and returns a `CompressedSegment`. ALSO writes one `compression_log` row per invocation (including NoOp per SC-013).

**Arguments**:

| Arg | Type | Notes |
|---|---|---|
| `payload` | str | The text to compress. For NoOp, returned verbatim. |
| `target_budget` | int | Target token count for `output_tokens`. Compressors that don't honour budget (NoOp) ignore. |
| `trust_tier` | str | One of `system` / `facilitator` / `participant_supplied`. Multi-tier callers MUST pre-resolve via `src/compression/trust_tier.py::resolve_min_tier(...)` before calling. |
| `compressor_id` | str \| None | Override the default selection. None = use `SACP_COMPRESSION_DEFAULT_COMPRESSOR` or `sessions.compression_mode` resolution. |
| `session_id` | str | Used for `compression_log.session_id`. |
| `participant_id` | str | Used for `compression_log.participant_id`. |
| `turn_id` | str | Used for `compression_log.turn_id`. |

**Returns**: `CompressedSegment` per `data-model.md`.

**Side effects**:
- One `compression_log` INSERT per invocation (FR-007 + SC-013).
- On non-NoOp success: emits `routing_log.reason='compression_applied'` (FR-003).
- On Compressor exception: emits `routing_log.reason='compression_pipeline_error'` (FR-020) AND raises `CompressionPipelineError` to the caller, which the bridge layer catches and falls through to un-compressed dispatch.

**Tier-1 refusal** (FR-014): when `trust_tier == 'system'`, raises `TierOneRefusalError` BEFORE invoking the compressor. The CompressorService catches and surfaces as `compression_pipeline_error`. NoOpCompressor is exempt — it produces byte-identical output and never inserts a compression artefact, so the protective rationale doesn't apply.

**Topology gate** (per `research.md §5`): when `SACP_TOPOLOGY=7`, the registry has `noop` only. Any non-NoOp `compressor_id` raises `UnregisteredCompressorError`.

## Performance budget (V14)

- NoOp dispatch overhead: < 1ms at P95 vs un-compressor-mediated baseline (asserted in `tests/test_026_perf_budgets.py`).
- Compressor body timing: recorded in `compression_log.duration_ms`. Phase 2 Layer 4 budget: ~200ms per 1K tokens on CPU.

## Read-only invariant

Registry contents are immutable after `freeze()`. The CompressorService MUST NOT issue any DB write OTHER THAN the per-dispatch `compression_log` INSERT. The architectural test `tests/test_026_architectural.py::test_compressor_service_has_no_unexpected_writes` enforces this.

## Cross-package import boundary (FR-023)

No file under `src/` outside `src/compression/` may import a concrete compressor (`NoOpCompressor`, `LLMLingua2mBERTCompressor`, `SelectiveContextCompressor`, `NoOpProvenceAdapter`, `NoOpLayer6Adapter`) directly. All access MUST go through `CompressorService.compress(...)`.

Architectural test: `tests/test_026_architectural.py::test_no_direct_compressor_imports_outside_compression_package`.
