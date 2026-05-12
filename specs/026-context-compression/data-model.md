# Data Model: Context Compression and Distillation (Six-Layer Stack)

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

Spec 026's data surface is one new table (`compression_log`), one new column (`sessions.compression_mode`), and a set of in-process types around the CompressorService registry. All schema additions ship in alembic revision `018` (pre-allocated; assumes 022's `017_detection_events.py` lands first per `feedback_parallel_merge_sequence_collisions`).

## `compression_log` (new persisted entity)

Append-only per-dispatch telemetry. One row per CompressorService.compress() invocation, including NoOp dispatches per Session 2026-05-11 §2.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | BIGSERIAL | NOT NULL | Primary key. Auto-generated. |
| `session_id` | TEXT | NOT NULL | The session whose turn produced this dispatch. Indexed; primary cross-spec read key. |
| `turn_id` | TEXT | NOT NULL | The turn id within the session. Joins to `routing_log.turn_id`. |
| `participant_id` | TEXT | NOT NULL | The participant whose outgoing window this dispatch targets. Per-participant pre-bridge placement per FR-010. |
| `source_tokens` | INTEGER | NOT NULL | Token count of the input payload BEFORE compression, measured via the target provider's TokenizerAdapter. |
| `output_tokens` | INTEGER | NOT NULL | Token count of the output payload AFTER compression. For NoOp dispatches, `output_tokens == source_tokens`. |
| `compressor_id` | TEXT | NOT NULL | One of: `noop`, `llmlingua2_mbert`, `selective_context`, `provence`, `layer6`. Resolved from `SACP_COMPRESSION_DEFAULT_COMPRESSOR` or `sessions.compression_mode`. |
| `compressor_version` | TEXT | NOT NULL | Semantic version of the compressor implementation. NoOp v1.0; LLMLingua-2 mBERT v0-scaffold in Phase 1, bumps to v1.0 at Phase 2 ship. |
| `trust_tier` | TEXT | NOT NULL | One of: `system`, `facilitator`, `participant_supplied`. MIN-tier of input segments per Session 2026-05-11 §3. NoOp preserves input tier verbatim. |
| `layer` | TEXT | NOT NULL | The compression layer name. Maps 1:1 to `compressor_id` for the registered compressors; redundant but kept for clearer cross-spec joins (e.g., spec 016 metrics groups by layer, not compressor_id). |
| `duration_ms` | REAL | NOT NULL | Per-call wall-clock timing of the compressor body. Computed via `time.perf_counter()` around `compressor.compress(...)`. V14 Layer 4 budget enforcement key. |
| `created_at` | TIMESTAMPTZ | NOT NULL | DEFAULT NOW(). |

**Constraints**:

```sql
CHECK (source_tokens >= 0)
CHECK (output_tokens >= 0)
CHECK (duration_ms >= 0)
CHECK (trust_tier IN ('system', 'facilitator', 'participant_supplied'))
CHECK (compressor_id IN ('noop', 'llmlingua2_mbert', 'selective_context', 'provence', 'layer6'))
```

**Indexes**:

- `compression_log_session_created_idx ON (session_id, created_at DESC)` — primary cross-spec read pattern.
- `compression_log_compressor_created_idx ON (compressor_id, created_at DESC)` — spec 016 metrics group-by-layer.

**Append-only invariant**: Per spec 001 §FR-008, no UPDATE or DELETE against this table. The application DB role has INSERT/SELECT only per Constitution §6.2. Migration is forward-only per §FR-017.

**Mirror in `tests/conftest.py`**: per `feedback_test_schema_mirror`. The DDL above is duplicated in the raw-DDL section of `tests/conftest.py`. The `scripts/check_schema_mirror.py` gate catches drift.

## `sessions.compression_mode` (new column)

Per-session override controlling compressor selection for dispatches in that session.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `compression_mode` | TEXT | NOT NULL | `'auto'` | One of: `auto`, `off`, `noop`, `llmlingua2_mbert`, `selective_context`, `provence`, `layer6`. CHECK constrained. |

**Semantics** (per FR-026 + `research.md §4`):

| Value | Effect |
|---|---|
| `auto` | CompressorService selects compressor per `SACP_COMPRESSION_DEFAULT_COMPRESSOR` + threshold rules. Phase 1: always resolves to `noop`. Phase 2: resolves to `llmlingua2_mbert` when projected tokens > `SACP_COMPRESSION_THRESHOLD_TOKENS`. |
| `off` | Forces NoOpCompressor regardless of threshold. `compression_log` still writes the per-dispatch row per FR-007 + SC-013. |
| `noop` | Same as `off` — explicit opt-in to the pass-through compressor. Operator-visible distinction from `auto`. |
| `llmlingua2_mbert` | Forces LLMLingua-2 mBERT. Requires `SACP_COMPRESSION_PHASE2_ENABLED=true` (else dispatch fails closed per FR-020). |
| `selective_context` | Forces Selective Context. Same Phase 2 gate as above. |
| `provence` | Forces Provence (Layer 5). Phase 3 scaffold; raises `NotImplementedError` until a retrieval spec ships. |
| `layer6` | Forces Layer 6 (Activation Beacon / ICAE / KV-cache). Phase 3 scaffold; closed-API legs skip per FR-022 + SC-011. |

**Backward compatibility**: existing sessions get `compression_mode='auto'` via the NOT NULL DEFAULT. No data backfill required.

**Constraint**:

```sql
CHECK (compression_mode IN ('auto', 'off', 'noop', 'llmlingua2_mbert', 'selective_context', 'provence', 'layer6'))
```

## `CompressedSegment` (in-process type)

Output of `CompressorService.compress(...)`. Lives at `src/compression/segments.py`. Not persisted directly; columns feed into `compression_log` row writes and into the XML boundary marker assembly.

| Field | Type | Notes |
|---|---|---|
| `output_text` | str | The compressed (or NoOp pass-through) payload. |
| `output_tokens` | int | Token count of `output_text`. |
| `trust_tier` | str | Resolved MIN-tier from input segments per Session 2026-05-11 §3. For NoOp, equals input tier. |
| `boundary_marker` | str \| None | The XML boundary marker wrapping `output_text`, or None for NoOp. Format per `research.md §7`. |
| `compressor_id` | str | One of the registered compressor ids. |
| `compressor_version` | str | The compressor's `COMPRESSOR_VERSION` class attribute. |

The bridge layer wraps `output_text` with `boundary_marker` BEFORE dispatch when `boundary_marker is not None`. NoOp leaves the payload bare (byte-identical to un-compressor-mediated dispatch per SC-006).

## `CompressorService` registry (in-process state)

Process-scope registry mapping `compressor_id → compressor_class`. Read-only after `freeze()` invoked at orchestrator startup. Module-load registration pattern per `research.md §5`.

| Field | Type | Notes |
|---|---|---|
| `_registry` | dict[str, type[Compressor]] | The internal registry; populated at module import time. |
| `_frozen` | bool | False during startup; True after the FastAPI lifespan calls `freeze()`. Register-after-freeze raises RuntimeError. |

**Topology gate** (per `research.md §5` + spec §V12): when `SACP_TOPOLOGY=7`, the registry initialises with `noop` only — Phase 2/3 compressors do not register.

## routing_log `reason` enum additions (application-level; no DDL change)

Five new values for the existing `routing_log.reason` TEXT column. No migration required.

| Value | Emitted at | Source spec |
|---|---|---|
| `cache_hit` | `src/api_bridge/caching.py` response-handling site, after LiteLLM response indicates cache hit. | 026 FR-003 |
| `cache_miss` | Same site, after cache miss. | 026 FR-003 |
| `compression_applied` | `src/compression/service.py` after a successful non-NoOp compress(). | 026 FR-003 |
| `compression_pipeline_error` | `src/compression/service.py` catch-handler around any Compressor exception. | 026 FR-020 |
| `density_anomaly_flagged` | `src/orchestrator/density.py` per-turn dual-write (alongside the existing `convergence_log` write). | 026 FR-018 + Session 2026-05-11 §4 |

## Class-mapping registry (in-process, hardcoded)

`src/compression/service.py` keeps a hardcoded list of registered compressor ids for validation and error messages:

```python
COMPRESSOR_IDS: frozenset[str] = frozenset([
    "noop",
    "llmlingua2_mbert",
    "selective_context",
    "provence",
    "layer6",
])
```

**Mutability**: process-scope read-only. Adding a compressor requires a spec amendment + a module addition + registry update; spec 026 FR-006 fixes the registry shape, not the membership (membership extensions are allowed via future specs).

## TokenizerAdapter (existing, no changes)

Per `research.md §1`, `src/api_bridge/tokenizer.py` already ships the TokenizerAdapter Protocol with three implementations (OpenAI tiktoken, Anthropic, Gemini). Spec 026 documents the integration boundary in research and consumes the adapter via:

```python
from src.api_bridge.tokenizer import get_tokenizer_for_provider
tokenizer = get_tokenizer_for_provider(provider)
token_count = tokenizer.count_tokens(payload)
```

No module changes from spec 026 — the adapter is the source-of-truth for the `source_tokens` / `output_tokens` columns in `compression_log`.

## V18 derived-artifact traceability

Every compressed segment carries the XML boundary marker (`<compressed source-tier="..." compressor="..." version="..." />`) recording the compressor id + version + trust tier. The corresponding `compression_log` row records source_tokens + output_tokens + duration_ms. A reviewer can:

1. See a compressed segment in a dispatched window
2. Read the marker to get compressor_id + version + tier
3. Query `compression_log WHERE turn_id = <X> AND participant_id = <Y>` to find the canonical telemetry row
4. From the row, see source_tokens (input size) and output_tokens (output size) for that exact dispatch

The derivation method (which compressor + which version + which trust tier) is encoded in the marker; the per-dispatch telemetry is in the log table. Together they satisfy V18 traceability.

## Migration: alembic `018_compression_log.py`

**Pre-allocated revision**: `018`. Assumes spec 022's `017_detection_events.py` lands first. If 026 lands first, swap to `017` and renumber 022 (coordination per `feedback_parallel_merge_sequence_collisions`).

**Upgrade**:

```python
def upgrade() -> None:
    op.create_table(
        "compression_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("turn_id", sa.Text, nullable=False),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column("source_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("compressor_id", sa.Text, nullable=False),
        sa.Column("compressor_version", sa.Text, nullable=False),
        sa.Column("trust_tier", sa.Text, nullable=False),
        sa.Column("layer", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Float, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("source_tokens >= 0", name="compression_log_source_tokens_nonneg"),
        sa.CheckConstraint("output_tokens >= 0", name="compression_log_output_tokens_nonneg"),
        sa.CheckConstraint("duration_ms >= 0", name="compression_log_duration_ms_nonneg"),
        sa.CheckConstraint(
            "trust_tier IN ('system', 'facilitator', 'participant_supplied')",
            name="compression_log_trust_tier_enum",
        ),
        sa.CheckConstraint(
            "compressor_id IN ('noop', 'llmlingua2_mbert', 'selective_context', 'provence', 'layer6')",
            name="compression_log_compressor_id_enum",
        ),
    )
    op.create_index(
        "compression_log_session_created_idx",
        "compression_log",
        ["session_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "compression_log_compressor_created_idx",
        "compression_log",
        ["compressor_id", sa.text("created_at DESC")],
    )
    op.add_column(
        "sessions",
        sa.Column("compression_mode", sa.Text, nullable=False, server_default="auto"),
    )
    op.create_check_constraint(
        "sessions_compression_mode_enum",
        "sessions",
        "compression_mode IN ('auto', 'off', 'noop', 'llmlingua2_mbert', 'selective_context', 'provence', 'layer6')",
    )
```

**Downgrade**: no-op (matches the existing 011/013/014/015 pattern; forward-only per spec 001 §FR-017).

**Test fixture**: `tests/test_026_migration_018.py` applies the migration to a fresh schema and asserts table + column + indexes + constraints exist.
