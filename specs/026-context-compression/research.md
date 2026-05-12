# Research: Context Compression and Distillation (Six-Layer Stack)

**Branch**: `026-context-compression` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Phase 0 research for spec 026. Sixteen sections covering (a) the existing Phase 1 surface already shipped via fix/* PRs that 026 formalises, and (b) the new surface 026 introduces. The architectural decisions are fixed by the project's compression research bundle per spec §"Clarifications" — research here resolves implementation-level questions only.

## §1 — Existing Phase 1 surface audit (what's shipped)

**Context**: Spec 026 is explicitly NOT a clean scaffold-only spec. Several Phase 1 Layer 1/2/3 deliverables already shipped via fix/* PRs. Audit before designing new surface.

**Shipped surface** (verified 2026-05-11):

- **[src/api_bridge/caching.py](../../src/api_bridge/caching.py)** — Layer 1 Anthropic `cache_control` directives + OpenAI `prompt_cache_key` + Gemini placeholder. Per-provider translation that the bridge applies before the LiteLLM call. `CacheDirectives` dataclass + `BreakpointPosition` enum. Default Anthropic TTL is `1h`. Gated by `SACP_CACHING_ENABLED` (default `1`).
- **[src/api_bridge/tokenizer.py](../../src/api_bridge/tokenizer.py)** — TokenizerAdapter Protocol with three concrete implementations (OpenAI tiktoken, Anthropic via cl100k_base × 1.10 multiplier with `count_tokens` reconciliation path, Gemini via cl100k_base × 0.95 multiplier with `countTokens` reconciliation path). Solves the FR-015 requirement.
- **[src/orchestrator/density.py](../../src/orchestrator/density.py)** — information-density signal. Phase 1 observational; writes to `convergence_log` with `tier='density_anomaly'`. No escalation in Phase 1.
- **[src/config/validators.py](../../src/config/validators.py)** — three already-registered validators: `SACP_ANTHROPIC_CACHE_TTL` (line 255), `SACP_CACHING_ENABLED` (line 274), `SACP_DENSITY_ANOMALY_RATIO` (line 279).
- **[docs/env-vars.md](../../docs/env-vars.md)** — sections for `SACP_CACHING_ENABLED` (line 131), `SACP_ANTHROPIC_CACHE_TTL` (line 140), `SACP_DENSITY_ANOMALY_RATIO` (line 158).

**Gap**: the routing_log `cache_hit` / `cache_miss` markers (FR-003) are NOT yet wired at the response-handling site. The summarizer-corpus filter for density-flagged turns (FR-019) is NOT yet wired. These two pieces are the Phase 1 behavioural deltas spec 026 ships.

**Action**: spec 026 does NOT refactor the shipped modules. The compressor package lives at `src/compression/` and the existing modules stay where they are; spec 026 documents the integration boundary instead.

## §2 — Env-var name reconciliation (rename direction: spec → code)

**Context**: Spec 026 names six env vars. Two collide in name with already-shipped validators in `src/config/validators.py`. The names differ:

| Spec 026 name (drafted) | Shipped name | Decision |
|---|---|---|
| `SACP_CACHE_ANTHROPIC_TTL` | `SACP_ANTHROPIC_CACHE_TTL` | Use the shipped name. Update spec text at tasks-time. |
| `SACP_INFORMATION_DENSITY_THRESHOLD` | `SACP_DENSITY_ANOMALY_RATIO` | Use the shipped name. Update spec text at tasks-time. |
| `SACP_CACHE_OPENAI_KEY_STRATEGY` | (not shipped) | NEW — add to validators + docs. |
| `SACP_COMPRESSION_PHASE2_ENABLED` | (not shipped) | NEW — add to validators + docs. |
| `SACP_COMPRESSION_THRESHOLD_TOKENS` | (not shipped) | NEW — add to validators + docs. |
| `SACP_COMPRESSION_DEFAULT_COMPRESSOR` | (not shipped) | NEW — add to validators + docs. |

**Decision**: Code is source of truth. Renaming the shipped validators + their consumers + the docs sections would touch >10 files for cosmetic alignment. The spec text rename is a single-paragraph edit. Tasks T0XX-T0YY add an inline header note to `docs/env-vars.md` cross-referencing both names so operators searching either find the right doc.

**Rationale**: The shipped names are already in operator-facing surfaces — `.env` files in deployed stacks (see memory `project_deploy_dockge_truenas`), Dockge stack config at `/mnt/.ix-apps/app_mounts/dockge/stacks/sacp/`, internal documentation pointing at the shipped names. Renaming risks silent breakage on next deploy. Spec text is the canonical artefact moving forward but it follows the code, not vice versa.

**Spec text update** (at tasks-time, NOT in this PR): the `## Configuration (V16) — New Env Vars` section ships in tasks.md as a coordinated amendment that aligns the names. Cross-ref FR-025.

## §3 — `compression_log` table shape

**Context**: Per Session 2026-05-11 §1 + FR-005, a dedicated `compression_log` table ships with the column set drafted in FR-005. Including `duration_ms` per the V14 Layer 4 budget surface.

**DDL** (alembic revision 018, forward-only per spec 001 §FR-017):

```sql
CREATE TABLE compression_log (
    id            BIGSERIAL PRIMARY KEY,
    turn_id       TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    source_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    compressor_id TEXT NOT NULL,
    compressor_version TEXT NOT NULL,
    trust_tier    TEXT NOT NULL,
    layer         TEXT NOT NULL,
    duration_ms   REAL NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX compression_log_session_created_idx
    ON compression_log (session_id, created_at DESC);
CREATE INDEX compression_log_compressor_created_idx
    ON compression_log (compressor_id, created_at DESC);
```

**`session_id` column rationale**: not in the FR-005 drafted column set; added here because cross-spec read patterns (spec 016 metrics, spec 011 admin panel, spec 010 debug export) all key on `session_id`. Without it, joining via `turn_id → routing_log → session_id` is wasteful. The addition is a strict superset of the drafted shape; the spec text update is a one-line addition at tasks-time.

**Constraint check**: `CHECK (output_tokens >= 0 AND source_tokens >= 0)` and `CHECK (duration_ms >= 0)` — sanity bounds against negative values from a buggy compressor.

**Mirror in `tests/conftest.py`**: per `feedback_test_schema_mirror`, this DDL is duplicated in the raw-DDL section of `tests/conftest.py` so CI builds the schema from conftest, not migrations. The `scripts/check_schema_mirror.py` gate catches drift.

**Retention**: append-only per spec 001 §FR-008. Retention follows the existing `SACP_LOG_RETENTION_DAYS` envelope (spec 010 §FR-005); spec 026 does NOT introduce a new retention env var.

## §4 — `sessions.compression_mode` column

**Context**: Per FR-026, `sessions.compression_mode` accepts `auto` | `off` | `<layer-name>` values.

**DDL addition** (same alembic 018 migration):

```sql
ALTER TABLE sessions
ADD COLUMN compression_mode TEXT NOT NULL DEFAULT 'auto'
CHECK (compression_mode IN ('auto', 'off', 'noop', 'llmlingua2_mbert', 'selective_context', 'provence', 'layer6'));
```

**Semantics**:
- `auto` (default): the dispatch path selects compressor per `SACP_COMPRESSION_DEFAULT_COMPRESSOR` + threshold rules. In Phase 1 this resolves to `noop` for all dispatches; in Phase 2 it resolves to `llmlingua2_mbert` once `SACP_COMPRESSION_PHASE2_ENABLED=true` AND the projected token count exceeds `SACP_COMPRESSION_THRESHOLD_TOKENS`.
- `off`: dispatch path uses NoOpCompressor regardless of threshold. `compression_log` still writes a row per FR-007 + SC-013 — the `layer='noop'` value signals operator intent.
- `<layer-name>`: force a specific layer for the session. The compressor registry resolves the value; unregistered names cause dispatch fail-closed with `routing_log.reason='compression_pipeline_error'` per FR-020.

**Mirror in `tests/conftest.py`**: per `feedback_test_schema_mirror`.

## §5 — `CompressorService` interface design

**Context**: Per FR-006, a `CompressorService` interface MUST be defined with at minimum `compress(payload, target_budget, trust_tier) -> CompressedSegment` and `register(compressor_id, compressor_class)`. Implementations register at module load time; the registry is read-only after orchestrator startup.

**Interface shape** (`src/compression/service.py`):

```python
class CompressorService:
    """Process-scope compressor registry. Read-only after startup."""

    def __init__(self) -> None:
        self._registry: dict[str, type[Compressor]] = {}
        self._frozen: bool = False

    def register(self, compressor_id: str, compressor_class: type[Compressor]) -> None:
        if self._frozen:
            raise RuntimeError("CompressorService is read-only after startup; register at module load time")
        self._registry[compressor_id] = compressor_class

    def freeze(self) -> None:
        self._frozen = True

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
    ) -> CompressedSegment:
        compressor_id = compressor_id or os.environ["SACP_COMPRESSION_DEFAULT_COMPRESSOR"]
        compressor_class = self._registry[compressor_id]  # KeyError -> caller handles fail-closed
        compressor = compressor_class()
        # ... per-call timing + log_compression_event ...
        return compressor.compress(payload, target_budget, trust_tier)
```

**Module-load registration pattern**: each compressor module calls `CompressorService.register(...)` at import time. The orchestrator's FastAPI lifespan invokes `freeze()` once at startup before the first dispatch; subsequent `register()` calls raise. This matches spec 020's `AdapterRegistry` lifecycle.

**Topology gate**: when `os.environ.get('SACP_TOPOLOGY') == '7'`, the registry initialises with `noop` only — Phase 2/3 compressors do not register because topology 7's per-MCP-client provider settings are the only Layer 1 hook (spec §V12). Same forward-document pattern as specs 014/020/021/023/025.

## §6 — NoOpCompressor + log-on-noop pattern

**Context**: Per Session 2026-05-11 §2 + FR-007, NoOpCompressor writes a `compression_log` row on every dispatch. Phase 1 baseline telemetry for the Phase 2 cutover.

**Implementation** (`src/compression/noop.py`):

```python
class NoOpCompressor(Compressor):
    COMPRESSOR_ID = "noop"
    COMPRESSOR_VERSION = "1"

    def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
        return CompressedSegment(
            output_text=payload,                        # byte-identical to input
            output_tokens=count_tokens(payload, ...),   # count via TokenizerAdapter
            trust_tier=trust_tier,                       # pass-through; MIN-tier applies only on real compression
            boundary_marker=None,                        # NoOp produces no marker; the input IS the canonical output
            compressor_id=self.COMPRESSOR_ID,
            compressor_version=self.COMPRESSOR_VERSION,
        )
```

**SC-006 byte-identical invariant**: NoOp output_text MUST equal input payload bit-for-bit. Asserted in `tests/test_026_noop_compressor.py`.

**SC-013 log-per-dispatch invariant**: every CompressorService.compress() call (including NoOp) writes one `compression_log` row. The log_compression_event(...) call lives at the CompressorService level, NOT inside each Compressor implementation, so the invariant holds by construction (the wrapping is shared).

**duration_ms for NoOp**: measured via `time.perf_counter()` around the `compressor.compress()` call. NoOp values are typically < 1ms; recording them preserves the per-dispatch baseline.

## §7 — XML boundary markers + trust-tier inheritance

**Context**: Per FR-011 + FR-012 + Session 2026-05-11 §3, compressed segments inherit MIN-tier of source segments and carry XML boundary markers.

**Marker shape**:

```xml
<compressed source-tier="participant_supplied" compressor="llmlingua2_mbert" version="1.0">
... compressed text ...
</compressed>
```

**MIN-tier resolution** (`src/compression/trust_tier.py`):

```python
TIER_ORDER = ["system", "facilitator", "participant_supplied"]  # high → low

def resolve_min_tier(source_tiers: list[str]) -> str:
    return min(source_tiers, key=lambda t: TIER_ORDER.index(t))
```

**Tier-1 refusal** (FR-014): compressors check `trust_tier == 'system'` at entry and raise `TierOneRefusalError`. The CompressorService catches this and falls through to un-compressed dispatch with `routing_log.reason='compression_pipeline_error'` per FR-020. Architectural test asserts every Compressor implementation has the tier-1 check at the top of `compress(...)`.

**NoOp exception**: NoOpCompressor does NOT apply tier-1 refusal because it produces byte-identical output (the protective rationale doesn't apply — no compression artefact is being inserted). The tier-1 refusal applies only to compressors that actually reshape content (LLMLingua-2, Selective Context, Provence, Layer 6).

## §8 — LLMLingua-2 mBERT integration (Phase 2 scaffold)

**Context**: Per FR-008, `LLMLingua2mBERTCompressor` is the Phase 2 default once `SACP_COMPRESSION_PHASE2_ENABLED=true`. Spec 026 Phase 1 ships the scaffold only — the real integration lands at Phase 2 task time.

**Phase 1 scaffold shape** (`src/compression/llmlingua2_mbert.py`):

```python
class LLMLingua2mBERTCompressor(Compressor):
    COMPRESSOR_ID = "llmlingua2_mbert"
    COMPRESSOR_VERSION = "0-scaffold"   # bumps to "1" when Phase 2 ships real implementation

    def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
        if os.environ.get("SACP_COMPRESSION_PHASE2_ENABLED") != "true":
            raise NotImplementedError("Phase 2 not enabled; set SACP_COMPRESSION_PHASE2_ENABLED=true to opt in")
        # Phase 2 task list adds the real `llmlingua` import + model load + .compress_prompt() call
        raise NotImplementedError("Phase 2 task list NNN implements the real compressor body")
```

**Dependency note**: `pip install llmlingua` brings `transformers` + `accelerate` + `nltk` + `torch`. ~2 GB on disk. Phase 2 PR documents the supply-chain stance and hash-locks per Constitution §6.3.

**Selective Context A/B**: per FR-009, `SelectiveContextCompressor` ships as the Phase 2 fallback. The A/B harness is conditional on Phase 2 implementation; v1 ships LLMLingua-2 as default and leaves the A/B for Phase 2 work per spec Clarifications §"Empirical defaults requiring calibration".

## §9 — Selective Context fallback (Phase 2 scaffold)

**Context**: Per FR-009, `SelectiveContextCompressor` is the Phase 2 fallback. Same scaffold pattern as §8 — `NotImplementedError` until Phase 2 enabled.

**Phase 2 implementation note** (for Phase 2 task list, NOT this PR): Selective Context uses a small LM (typically GPT-2) to score per-token self-information; tokens below a threshold are dropped. The 2024 paper benchmark showed lower latency than LLMLingua-2 mBERT on short inputs but higher token loss. The fallback role: when LLMLingua-2 mBERT exceeds the per-call latency budget on a participant's traffic, switch to Selective Context.

## §10 — Provence stub (Phase 3 scaffold)

**Context**: Per FR-021, Layer 5 (Provence) registers a stub adapter in v1. Real adapter lands in the retrieval spec when retrieval enters the design.

**Stub shape** (`src/compression/provence.py`):

```python
class NoOpProvenceAdapter:
    COMPRESSOR_ID = "provence"
    COMPRESSOR_VERSION = "0-stub"

    def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
        # Layer 5 only fires on the retrieval path. No retrieval surface exists yet.
        raise NotImplementedError("Layer 5 Provence requires a retrieval surface; not in current Phase 3 specs")
```

The adapter registers at module-import time so the registry has the slot; the implementation is unreachable until a retrieval spec lands.

## §11 — Layer 6 stub (Phase 3 scaffold)

**Context**: Per FR-022, Layer 6 (Activation Beacon, ICAE, KV-cache) registers a stub adapter. Real adapter lands in the local-model-support spec. Layer 6 MUST be structurally skipped on closed-API legs (no error; the layer is inapplicable).

**Stub shape** (`src/compression/layer6.py`):

```python
class NoOpLayer6Adapter:
    COMPRESSOR_ID = "layer6"
    COMPRESSOR_VERSION = "0-stub"

    @classmethod
    def supports(cls, provider: str) -> bool:
        """Layer 6 applies only to open-weight legs (ollama, vllm). Closed-API legs return False."""
        return provider in ("ollama", "vllm")

    def compress(self, payload: str, target_budget: int, trust_tier: str) -> CompressedSegment:
        raise NotImplementedError("Layer 6 requires local-model support; not in current Phase 3 specs")
```

**Skip path**: the dispatch path calls `NoOpLayer6Adapter.supports(provider)` BEFORE invoking `.compress()`. On closed-API legs (`anthropic`, `openai`, `google`), the result is False and the dispatch path skips Layer 6 entirely without error. SC-011 verifies this.

## §12 — routing_log enum additions

**Context**: Per FR-003 + FR-018 + Session 2026-05-11 §4 dual-write, five new `routing_log.reason` values land: `cache_hit`, `cache_miss`, `compression_applied`, `compression_pipeline_error`, `density_anomaly_flagged`.

**No DDL change**: `routing_log.reason` is a TEXT column (not a Postgres enum), so the additions are application-level. The spec 003 §FR-030 routing_log reason enumeration in code is updated; any constants list in `src/repositories/log_repo.py` (or wherever the reasons live) gets the five additions.

**Emission sites**:
- `cache_hit` / `cache_miss` → `src/api_bridge/caching.py` response-handling site. Wire at task time; the helper at this site receives the per-call cache status from the LiteLLM response and emits the routing_log row.
- `compression_applied` → `src/compression/service.py` after a successful real-compression dispatch (LLMLingua-2, Selective Context). NoOp dispatches do NOT emit `compression_applied` (the marker semantics is "real compression ran"); they emit nothing on the compression axis.
- `compression_pipeline_error` → `src/compression/service.py` catch-handler around any Compressor exception, then fall through to un-compressed dispatch per FR-020.
- `density_anomaly_flagged` → `src/orchestrator/density.py` per Session 2026-05-11 §4 dual-write. The convergence_log row continues to write per spec 004 §FR-020; routing_log adds the per-turn-decision marker in the same transaction.

## §13 — Summarizer corpus filter for density anomalies (FR-019 — new Phase 1 behavioural change)

**Context**: Per FR-019, the summarizer (spec 005) MUST filter density-flagged turns from the summarizer corpus. This is the ONE new Phase 1 behavioural change beyond formalisation.

**Implementation**: the spec 005 summarizer reads recent turns from the message store and computes the rolling summary. Spec 026 adds a JOIN-or-filter step: for each candidate turn, check whether a `convergence_log` row with `tier='density_anomaly'` and `target_event_id=<turn_id>` exists; if yes, exclude the turn from the summarizer corpus.

**Implementation site**: wherever spec 005 reads turns for the rolling summary. The exact module path is determined at task time (the spec 005 implementation lives at `src/orchestrator/summarization.py` per the repo layout convention). Tasks T0XX adds the filter step + a test asserting flagged turns don't appear in the summarizer corpus.

**Test fixture**: insert a density-anomaly convergence_log row for a known turn; trigger the summarizer; assert the turn's content does NOT appear in the rolling-summary output.

**Backward-compat**: Phase 1 sessions running without the filter (sessions created before this PR lands) produce slightly different summaries on first re-summarisation. The change is observational-positive — flagged turns SHOULD have been excluded — but operators may notice the delta. Tasks T0XX documents this in the implementation-phase note.

## §14 — V14 budget instrumentation hooks

**Context**: Spec §V14 declares four budgets. Each MUST be observable in structured logs.

**Hooks**:

- **Layer 1 (caching)**: cache_hit / cache_miss / cache invalidation markers in `routing_log` (§12). No additional timing instrumentation — the gain is provider-side TTFT, observable from the existing `routing_log.duration_ms` (spec 003 §FR-031).
- **Layer 4 (LLMLingua-2 mBERT)**: per-call timing recorded in `compression_log.duration_ms`. Computed via `time.perf_counter()` in `CompressorService.compress(...)` wrapping each compressor call.
- **CompressorService dispatch overhead**: baseline NoOp dispatch overhead is measured in `tests/test_026_perf_budgets.py` against the un-compressor-mediated baseline. The test asserts NoOp dispatch adds < 1ms to the per-turn latency at the 95th percentile (the abstraction MUST NOT introduce buffering, copying, or serialization).
- **Information-density signal**: zero additional cost; reuses spec 021 §FR-011 `shaping_score_ms` timing inclusive of density evaluation per existing spec 004 instrumentation.

## §15 — Architectural test patterns

**Context**: FR-023 + FR-024 require two architectural tests.

**FR-023 — Compressor-package import boundary**:

```python
# tests/test_026_architectural.py
import ast
from pathlib import Path

def test_no_direct_compressor_imports_outside_compression_package():
    for src_file in Path("src").rglob("*.py"):
        if "src/compression/" in str(src_file):
            continue  # internal package files may import each other
        tree = ast.parse(src_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and any(node.module.endswith(c) for c in ("noop", "llmlingua2_mbert", "selective_context", "provence", "layer6")):
                    raise AssertionError(f"{src_file} imports a concrete compressor; use CompressorService instead")
```

**FR-024 — Raw-transcript convergence read**:

```python
# tests/test_026_architectural.py
def test_convergence_detector_reads_raw_transcript_not_bridge_view():
    # Inspect the convergence-detector entry-point in src/orchestrator/convergence.py
    # Assert it reads from the message-store interface (e.g., MessageRepository.list_recent_messages)
    # and NOT from the bridge view (e.g., BridgeAssembler.build_window).
    convergence_module = Path("src/orchestrator/convergence.py").read_text()
    assert "MessageRepository" in convergence_module
    assert "BridgeAssembler" not in convergence_module
```

The assertion is text-based (presence/absence of the relevant identifiers) rather than runtime-based because the convergence detector path is heavy to instantiate in a unit test. Acceptable per the spec 022 / 029 architectural-test precedent.

## §16 — Spec 011 amendment surface (admin metrics panel)

**Context**: Per `reminder_spec_011_amendments_at_impl_time.md`, spec 011 UI FRs deferred to implementation time. Spec 026 contributes admin-panel metrics surfaces:

- Cache hit rate (per session + per participant)
- Compression ratio (output_tokens / source_tokens, per dispatch / per session)
- Information-density baseline + recent flagged-turn count

**Amendment FR set** (drafted for tasks-time):

- FR-035: Admin panel SHALL expose a "Compression Metrics" page accessible from the existing admin dashboard. Master-switch gated.
- FR-036: The Compression Metrics page SHALL display per-session cache hit rate (graph: hits/min over time + cumulative %), compression ratio (graph: per-dispatch + rolling avg), and density baseline + recent flagged-turn count.
- FR-037: The page SHALL link to the underlying `compression_log` rows for the displayed session via the spec 022-style detail-row drill-down pattern.

**Implementation note**: this is a coordinated amendment between spec 011 and spec 026. At tasks-time, append the three FRs to `specs/011-web-ui/spec.md` per the established pattern (spec 022 T021 set the precedent).

## Outstanding from clarify (none)

All four [NEEDS CLARIFICATION] markers resolved in Session 2026-05-11. No deferred items remain at the Phase 0 level. Empirical-default calibration (4K threshold tuning, density-ratio tuning, LLMLingua-2 vs Selective Context A/B) is Phase-1-traffic-gated per the spec's own framing and explicitly NOT a clarification candidate.

## Summary

Sixteen Phase 0 research items resolved. The load-bearing reconciliation (§2 env-var names) preserves operator-facing surfaces. The Phase 1 surface audit (§1) identifies the two new behavioural changes (cache_hit/miss routing_log wiring + summarizer corpus filter) and confirms that the rest of Phase 1 is formalisation of already-shipped code. The schema additions (§3 compression_log + §4 sessions.compression_mode) are bounded to one migration. The compressor package design (§5-§11) keeps Phase 2 + Phase 3 scaffolds in tree without behavioural activation. The routing_log additions (§12), summarizer filter (§13), V14 instrumentation (§14), architectural tests (§15), and spec 011 amendment surface (§16) round out the implementation contract. Ready for `/speckit.tasks` once data-model.md and contracts/ land.
