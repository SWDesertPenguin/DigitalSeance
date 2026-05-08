# Contract: filler-scorer adapter interface

The filler scorer is a pure function over a candidate draft that consumes three signal sources and aggregates them into a single score. Adapters live in `src/orchestrator/shaping.py`.

## Top-level entry point

```python
def compute_filler_score(
    *,
    draft_text: str,
    profile: BehavioralProfile,
    engine: ConvergenceEngine,
) -> FillerScore:
    """Score a candidate draft on three filler signals.

    Pure function — no side effects, no DB writes. Reads the engine's
    in-memory recent-embeddings ring buffer (no DB read).

    Returns a FillerScore with the aggregate value and per-signal breakdown.
    """
```

`FillerScore` shape per [data-model.md](../data-model.md#fillerscore).

## Three signal helpers

Each helper returns a float in `[0.0, 1.0]`. The aggregate is the weighted sum of the three signals using the profile's per-family weights.

### Hedge-to-content ratio

```python
def _hedge_signal(draft_text: str) -> float:
    """Proportion of hedging tokens to total whitespace-split tokens."""
```

- Lowercases the draft and counts case-insensitive matches against the hardcoded `_HEDGE_TOKENS` tuple (per [research.md §3](../research.md)).
- Denominator: total whitespace-split token count of the draft (no tokenizer load).
- Already in `[0.0, 1.0]` by construction.
- Empty draft (zero tokens) returns `0.0` (no signal — also short-circuits the rest of the pipeline upstream).

### Restatement (cosine similarity vs prior 1-3 turns)

```python
def _restatement_signal(
    draft_text: str,
    engine: ConvergenceEngine,
) -> float:
    """Max cosine similarity vs the prior 1-3 turns' embeddings."""
```

- Reads `engine.recent_embeddings(depth=3)` (per [research.md §2](../research.md)) — returns up to three `bytes` values from the engine's in-memory ring buffer.
- Computes the candidate draft's embedding via the same async helper used in convergence.py (`_compute_embedding_async`); reuses the already-loaded sentence-transformers model — no second model load, in keeping with FR-012.
- Cosine similarity computed against each ring-buffer entry; max is returned.
- When the ring buffer is empty (first turn), returns `0.0` (no signal).
- When the sentence-transformers model is unavailable (raises on call), returns `0.0` and logs a warning per spec edge case ("Sentence-transformers embedding pipeline (spec 004) is unavailable").
- Already in `[0.0, 1.0]` because `normalize_embeddings=True` keeps cosine similarity non-negative for normalized vectors.

### Boilerplate closing detection

```python
def _closing_signal(draft_text: str) -> float:
    """Capped count of closing-pattern matches against the draft."""
```

- Counts regex matches against the hardcoded `_CLOSING_PATTERNS` tuple (per [research.md §3](../research.md)).
- Capped at 3 matches: returns `min(matches, 3) / 3.0`.
- Already in `[0.0, 1.0]` by construction.
- Patterns include common sign-offs ("hope this helps", "let me know if", "best regards", "cheers", "in summary", "to conclude", etc.) — full list in [research.md §3](../research.md).

## Aggregation

```python
def _aggregate(
    *,
    hedge: float,
    restatement: float,
    closing: float,
    profile: BehavioralProfile,
) -> float:
    return (
        profile.hedge_weight * hedge
        + profile.restatement_weight * restatement
        + profile.closing_weight * closing
    )
```

The three weights MUST sum to `1.0` per FR-002 — enforced as a module-load assertion against every entry in the `BEHAVIORAL_PROFILES` dict.

## Per-family `BehavioralProfile` dispatch

```python
def profile_for(provider_family: str) -> BehavioralProfile:
    """Look up the per-family BehavioralProfile.

    Raises KeyError if the family is not in the BEHAVIORAL_PROFILES dict
    (fail-loud: an unknown family at this point indicates a misconfigured
    participant, not a graceful-degradation case).
    """
    return BEHAVIORAL_PROFILES[provider_family]
```

Family lookup is from the participant's existing `provider_family` attribute — not a new env var, not a new config surface.

## Threshold resolution

```python
def threshold_for(profile: BehavioralProfile) -> float:
    """Resolve the effective threshold:
       - If SACP_FILLER_THRESHOLD env var is set, use that uniformly.
       - Otherwise use the per-family profile.default_threshold.
    """
```

The env var, when set, overrides every family's default uniformly per [research.md §9](../research.md). When unset, each family applies its own default.

## Retry orchestration

```python
async def evaluate_and_maybe_retry(
    *,
    draft: Draft,
    profile: BehavioralProfile,
    engine: ConvergenceEngine,
    dispatch: Callable[..., Awaitable[Draft]],
    compound_budget_remaining: int,
) -> tuple[Draft, ShapingDecision, int]:
    """Score the draft; if over threshold, fire up to 2 retries with the
    profile's retry_delta_text, bounded jointly by SHAPING_RETRY_CAP and
    the participant's compound-retry budget.

    Returns (persisted_draft, decision, retries_consumed).
    """
```

Implementation per [research.md §4](../research.md). Joint cap: shaping stops at whichever of `SHAPING_RETRY_CAP=2` (FR-004) or `compound_budget_remaining` (FR-006) is reached first.

## Per-stage cost capture

Each `compute_filler_score()` call runs inside `@with_stage_timing` (per V14). The stage name is `shaping_score_ms`. Each retry's dispatch runs inside its own `@with_stage_timing` with stage name `shaping_retry_dispatch_ms`. Both populate the corresponding `routing_log` columns per FR-011.

V14 budget: `shaping_score_ms` MUST track P95 <= 50ms per evaluation. Operators identify a regressing scorer by its cost profile via the standard routing-log per-stage query.

## Fail-closed contract

The scorer fail-closes on every internal error path:

| Failure mode | Behavior |
|---|---|
| `_HEDGE_TOKENS` regex / tokenization raises | Persist original draft; log `routing_log.shaping_reason='shaping_pipeline_error'`; do NOT retry. |
| Sentence-transformers model unavailable / raises | `_restatement_signal` returns `0.0`; warning log emitted; aggregate proceeds with hedge + closing only. Scorer continues. |
| `engine.recent_embeddings()` returns empty | `_restatement_signal` returns `0.0`; aggregate proceeds with hedge + closing only. Normal first-turn path. |
| `_CLOSING_PATTERNS` regex compile / match raises | Persist original draft; log `routing_log.shaping_reason='shaping_pipeline_error'`; do NOT retry. |
| Retry dispatch raises a provider error | Caught by the existing dispatch failure path (spec 003 §FR-031); the shaping retry consumes one slot of the compound-retry budget per FR-006. |

The session continues on every fail-closed path. One bad draft does not gate the loop, per spec edge-case rule.

## Independence from register-preset emission

The filler scorer does NOT read the participant's resolved register preset. The two dimensions compose at the prompt-assembly stage (the register-preset delta and the shaping-retry delta both feed `assemble_prompt` independently). When a shaping retry fires, the retry's prompt assembly includes BOTH the register-preset delta (still active) AND the shaping-retry delta — they are additive Tier 4 deltas.

## No cross-signal coupling

The three signal helpers do not call each other. The aggregator (`_aggregate`) collects each helper's float independently and applies the per-family weighted sum. This keeps signals independently testable (US1 acceptance scenarios).
