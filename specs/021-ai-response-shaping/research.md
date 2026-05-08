# Phase 0 Research: AI Response Shaping

Resolves the ten NEEDS CLARIFICATION items from `plan.md`. Spec-time clarifications (six items, resolved 2026-05-07) are NOT re-opened here — this document covers plan-time questions only.

## 1. Per-model `BehavioralProfile` shape

**Decision**: A frozen module-level `BEHAVIORAL_PROFILES` dict in `src/orchestrator/shaping.py`, keyed by provider family (string), with values shaped as a frozen dataclass:

```python
@dataclass(frozen=True)
class BehavioralProfile:
    default_threshold: float       # default SACP_FILLER_THRESHOLD when env unset; per-family
    hedge_weight: float            # default 0.5
    restatement_weight: float      # default 0.3
    closing_weight: float          # default 0.2
    retry_delta_text: str          # tightened Tier 4 delta for this family's retries
```

The dict carries entries for the six families enumerated in spec FR-003: `anthropic`, `openai`, `gemini`, `groq`, `ollama`, `vllm`. All six ship with the same `retry_delta_text` (the Direct preset's text per spec assumption) and the same default weights `(0.5, 0.3, 0.2)`; only `default_threshold` varies by family in v1 (anthropic and openai default `0.6`; gemini, groq, ollama, vllm default `0.55` reflecting observed terser baselines).

**Rationale**:
- Frozen dataclass values keep the dict immutable at module load — no race risk on read.
- Per-family `retry_delta_text` field exists in the schema even though all values are identical in v1 — leaves room for future per-family delta tuning without a future schema break (matches spec assumption "A learned per-model delta is a future spec enhancement").
- The threshold split (anthropic/openai higher than the others) reflects Phase 1+2 shakedown observations; calibration is documented in `quickstart.md` for operator review.

**Alternatives considered**:
- Dict-of-tuples instead of frozen dataclass — rejected. Tuples lose field-name ergonomics and make per-family tweaks harder to read in source.
- TOML/YAML config file loaded at startup — rejected for v1. Spec FR-003 explicitly mandates a hardcoded dict; per-model overrides land in a follow-up amendment per spec assumption.
- One global threshold with no per-family variation — rejected. Spec FR-003 says "MUST map each provider family to a default `SACP_FILLER_THRESHOLD` value plus default signal weights"; per-family threshold is required.

## 2. Restatement-overlap signal mechanics with spec 004

**Decision**: Add a `last_embedding` property and a small ring-buffer `_recent_embeddings` (depth 3, in-memory) on `ConvergenceEngine`. Single-point change in `src/orchestrator/convergence.py:177` where `similarity_score=similarity` is logged — also append the just-computed embedding to the ring buffer. The shaping pipeline reads via `engine.recent_embeddings()` (returns last 1-3 embeddings as a list of `bytes`), computes cosine similarity of the candidate draft's freshly-computed embedding against each entry, and takes the max as the restatement signal.

**Rationale**:
- Mirrors spec 014's `last_similarity` precedent — single-line read-only property pattern. Minimal coupling.
- Ring depth 3 matches FR-001's "prior 1-3 turns" wording exactly. No over-fetching from `convergence_log`.
- The candidate draft's embedding IS recomputed (the in-flight draft hasn't been logged to `convergence_log` yet at scoring time) — but it reuses the already-loaded sentence-transformers model on the orchestrator's existing thread-pool executor (`_compute_embedding_async` in convergence.py line 182). No second model load, in keeping with FR-012.
- Returning raw `bytes` rather than np.ndarray keeps the type matching the existing `convergence_log.embedding` column — the shaping module decodes via the same `np.frombuffer(..., dtype=np.float32)` pattern already in convergence.py.

**Hook contract** (minimal):
```python
class ConvergenceEngine:
    @property
    def last_embedding(self) -> bytes | None:
        """Most recent turn's embedding bytes, or None if no turn yet."""
        return self._last_embedding

    def recent_embeddings(self, depth: int = 3) -> list[bytes]:
        """Up to `depth` most recent embeddings, newest first.
        Returns shorter list when fewer turns have elapsed.
        """
        return list(self._recent_embeddings)[:depth]
```

Internal state: `_last_embedding: bytes | None` and `_recent_embeddings: collections.deque[bytes]` with `maxlen=3`. Both updated inside `_log_result` at the same point as the `similarity_score=similarity` log (line 177). Single-point change.

**Alternatives considered**:
- DB read of `convergence_log.embedding` on every shaping evaluation — rejected. Hot-path DB cost violates V14 budget 1 (P95 <= 50ms per draft).
- Cosine averaging across the 1-3 prior embeddings instead of `max` — rejected. `max` better captures "this draft restates the prior turn"; averaging dilutes a strong restatement signal across older context.
- Compute the candidate draft's embedding inside `ConvergenceEngine` and return the score directly — rejected. Couples spec 004 to spec 021's signal definition; the signal-computation stays in `shaping.py` to keep the dependency direction clean (021 → 004, never reversed).

## 3. Filler-scorer normalization & weight tuning

**Decision**: All three signal helpers return `[0.0, 1.0]` floats; the aggregate is the weighted sum (already-normalized weights summing to `1.0` per FR-002). Normalization rules:

- **Hedge-to-content ratio**: count hedging tokens in the draft (case-insensitive match against a hardcoded `_HEDGE_TOKENS` tuple), divide by total token count (tokenizer-free split on whitespace). Already in `[0.0, 1.0]` by definition.
- **Restatement (cosine similarity)**: compute cosine similarity of candidate draft's embedding against each entry of `engine.recent_embeddings(3)`; take the max. Cosine similarity is in `[-1.0, 1.0]` mathematically but spec 004's `_cosine_similarity_window` clamps to non-negative for normalized embeddings (`normalize_embeddings=True` in `_encode_text` line 197). So the value is already in `[0.0, 1.0]`.
- **Closing-pattern detection**: regex match count against a hardcoded `_CLOSING_PATTERNS` tuple, capped: `min(matches, 3) / 3.0`. Three-pattern cap matches observed Phase 1+2 shakedown drafts where multiple closing patterns ("Hope this helps!", "Let me know...", "Best regards") sometimes stack at once.

**Hardcoded token / pattern lists** (initial; tuned per quickstart calibration loop):

```python
_HEDGE_TOKENS = (
    "i think", "i believe", "perhaps", "maybe", "it seems", "it appears",
    "in my opinion", "from my perspective", "arguably", "presumably",
    "i would say", "i'd argue", "to some extent", "more or less",
    "kind of", "sort of", "in a sense", "if i may",
)

_CLOSING_PATTERNS = (
    r"\bhope (this|that) helps\b",
    r"\blet me know if\b",
    r"\bplease (feel free|don'?t hesitate)\b",
    r"\b(best|kind) regards\b",
    r"\bcheers!?\s*$",
    r"\bin (summary|conclusion)[,:]?\s",
    r"\bto (summarize|conclude|wrap up)[,:]?\s",
)
```

**Rationale**:
- Whitespace-split token counting avoids loading a tokenizer and stays under V14's 50ms budget.
- The hedge token list and closing-pattern list are starting defaults from Phase 1+2 shakedown observations; quickstart guides operators to grow the list via amendment when they observe family-specific patterns the defaults miss.
- The 3-pattern cap on closings prevents a draft with one extreme stacked closing from saturating the whole signal — the cap leaves headroom for the other two signals to contribute.

**Alternatives considered**:
- BPE tokenizer for hedge ratio — rejected. Adds a dependency or model load; whitespace split is sufficient for this signal's coarseness.
- Per-family hedge / closing pattern lists — rejected for v1. Default lists ship; operators can amend if observation justifies. Matches the spec assumption that per-model overrides land in a future amendment.
- Sigmoid normalization of the weighted sum — rejected. The weighted sum is already in `[0.0, 1.0]` because each component is in `[0.0, 1.0]` and the weights sum to `1.0`. No further normalization required.

## 4. Retry-budget threading through the dispatch path

**Decision**: Per-attempt budget consumption. The dispatch loop in `loop.py` calls the shaping evaluation AFTER each provider response, and the shaping orchestrator returns a tuple `(persisted_draft, retries_consumed: int)`. The dispatch loop subtracts `retries_consumed` from the participant's compound-retry budget (spec 003 §FR-031). When the compound budget reaches zero mid-shaping, the shaping loop exits early and persists the most recent draft (no further retries), and the dispatch loop's existing failure-path semantics fall through unchanged.

**Rationale**:
- Per-attempt consumption matches FR-006 wording ("Each tightened-delta retry MUST consume one attempt of the participant's provider compound-retry budget"). Pre-debit-the-worst-case would over-consume the budget when the first retry already passes threshold.
- Returning the consumed count keeps the dispatch loop's budget-tracking logic in one place — the shaping module doesn't reach into the participant's budget directly. Clean separation of concerns.
- Joint-cap behavior (FR-006 last sentence: "shaping stops at whichever cap is reached first") is implemented as: shaping loop exits when EITHER the hardcoded 2-retry cap fires OR the compound budget reaches zero. Both paths persist the most recent draft.

**Implementation sketch**:
```python
async def evaluate_and_maybe_retry(
    *,
    draft: Draft,
    profile: BehavioralProfile,
    engine: ConvergenceEngine,
    dispatch: Callable,           # closure over participant + tier
    compound_budget_remaining: int,
) -> tuple[Draft, int]:           # (persisted_draft, retries_consumed)
    score = compute_filler_score(draft, profile, engine)
    if score < threshold(profile):
        return draft, 0
    persisted = draft
    consumed = 0
    while consumed < SHAPING_RETRY_CAP and consumed < compound_budget_remaining:
        retry = await dispatch(tightened_delta=profile.retry_delta_text)
        consumed += 1
        retry_score = compute_filler_score(retry, profile, engine)
        log_routing(score=score, retry_score=retry_score, retry_text=profile.retry_delta_text)
        if retry_score < threshold(profile):
            return retry, consumed
        persisted = retry
        score = retry_score
    log_routing(reason="filler_retry_exhausted")
    return persisted, consumed
```

`SHAPING_RETRY_CAP = 2` is a module-level constant (the hardcoded cap from FR-004).

**Alternatives considered**:
- Pre-debit the worst-case (3 slots reserved upfront) — rejected. Over-consumes the budget when the first attempt passes threshold (zero retries fired but 3 slots gone). Misallocates budget to provider error retries that will never run for this turn.
- Make the shaping module own the budget directly — rejected. Couples the scorer to the participant-budget data structure; per-attempt return-tuple keeps the boundary clean.
- Block the dispatch loop on the shaping retry inline (no separate orchestration) — equivalent to per-attempt but harder to test in isolation. The function-with-closure approach lets shaping tests substitute a fixture dispatcher.

## 5. Register-state model — per-session vs per-participant resolution

**Decision**: SQL JOIN at `/me` query time. The `/me` endpoint's existing query gains a LEFT JOIN to `participant_register_override` (on participant_id) and a LEFT JOIN to `session_register` (on session_id). The resolved register slider is `COALESCE(override.slider_value, session.slider_value, SACP_REGISTER_DEFAULT)`. Same JOIN pattern is reused in the prompt assembly path (per-turn dispatch resolves the participant's effective register in one round trip).

**Rationale**:
- `/me` is not on the dispatch hot path — it's a participant-poll endpoint with read latencies measured in tens of milliseconds, not the sub-50ms V14 budget. The single round-trip cost is well within budget.
- Keeps the resolver stateless — no cache invalidation surface for the override-set or session-slider-change paths. Both writes simply UPDATE / INSERT the relevant table; the next `/me` or next turn picks up the change automatically.
- The COALESCE precedence (override → session → env-var default) directly encodes FR-007 / FR-008 / FR-009 / FR-010 without a separate resolver function.

**Resolved register source attribution**:
- Override row found → `register_source = 'participant_override'`.
- No override but session row found → `register_source = 'session'`.
- Neither found (fresh session, default applies) → still `register_source = 'session'` per spec FR-010 clarification (the env-var default is reported as the session's value).

**Alternatives considered**:
- Cached resolver on the session-runtime context — rejected. Adds invalidation surface (override-set, session-slider-change, override-clear, participant-leave, session-delete cascades). Two writes are the only state mutations; the SQL JOIN pays one round trip per read for that simplicity gain.
- Single `register_state` table holding both session-level and per-participant rows distinguished by a nullable `participant_id` — rejected. Cascade semantics are murkier (the override row would need a CHECK constraint to require participant_id when present); two narrow tables align cleanly with spec 001's atomic-delete contract.

## 6. `/me` payload extension shape

**Decision**: Add three new top-level fields to the `/me` JSON response, snake_case to match the existing convention:

```json
{
  // ... existing fields ...
  "register_slider": 4,
  "register_preset": "technical",
  "register_source": "session"
}
```

- `register_slider`: integer in `[1, 5]`. Always present once `/me` returns successfully.
- `register_preset`: one of `"direct"`, `"conversational"`, `"balanced"`, `"technical"`, `"academic"`. Resolved from the slider via `RegisterPreset` registry lookup.
- `register_source`: one of `"session"`, `"participant_override"` (per FR-010 two-value enum).

**Rationale**:
- Snake_case matches existing `/me` field naming (e.g., `participant_id`, `session_id`).
- Preset name as a string (not the slider int) avoids forcing clients to embed the registry mapping.
- Two-value `register_source` enum matches FR-010 exactly; the spec deliberately collapses "session row exists" and "session row defaulted from env" into a single `'session'` value.
- Additive change — clients that don't read the new fields are unaffected. No version bump required.

**Alternatives considered**:
- Nest the three fields under a `register: { ... }` sub-object — rejected. Existing `/me` is flat; nesting one feature's fields is inconsistent. Three top-level fields stay grep-able.
- Three-value `register_source` enum (`session`, `participant_override`, `default`) — rejected per spec FR-010 clarification (two-value enum collapses default into session).

## 7. Two-table vs one-table register persistence

**Decision**: Two new tables.

```sql
CREATE TABLE session_register (
    session_id              UUID PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    slider_value            INTEGER NOT NULL CHECK (slider_value BETWEEN 1 AND 5),
    set_by_facilitator_id   UUID NOT NULL REFERENCES facilitators(id),
    last_changed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE participant_register_override (
    participant_id          UUID PRIMARY KEY REFERENCES participants(id) ON DELETE CASCADE,
    session_id              UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    slider_value            INTEGER NOT NULL CHECK (slider_value BETWEEN 1 AND 5),
    set_by_facilitator_id   UUID NOT NULL REFERENCES facilitators(id),
    last_changed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX participant_register_override_session_idx
    ON participant_register_override(session_id);
```

**Rationale**:
- Keeps the `sessions` row narrow — matches spec 013's "frozen config + auxiliary mutable state in side tables" precedent.
- Both tables use `ON DELETE CASCADE` for both their natural foreign keys, which directly satisfies FR-015 / SC-007 (override row disappears on participant or session delete; no orphan rows).
- The override table's secondary `session_id` index supports the session-scoped query "list all overrides in this session" — useful for the audit-log diagnostic view in spec 011 (when that ships) and for the spec 011-amendment-time UI surface.
- PRIMARY KEY on `participant_id` enforces "zero or one override per participant" implicitly.

**Schema-mirror note**: Both tables MUST also be added to `tests/conftest.py` raw DDL. CI builds schema from conftest, not migrations — local DB tests skip without Postgres so a mismatch only surfaces in CI (per `feedback_test_schema_mirror.md`).

**Alternatives considered**:
- Nullable column on `sessions` table for the session slider value — rejected. Adds a column to a frequently-touched table; the side-table pattern matches spec 013/014 precedent.
- Single `register_state` table with nullable `participant_id` — rejected. Cascade semantics are messier and the COALESCE-based JOIN at `/me` time is harder to write cleanly.
- Store the override as a JSON blob on the `participants` row — rejected. Opaque to SQL queries; defeats the audit-log JOIN.

## 8. Audit-event taxonomy for register changes

**Decision**: Three new `admin_audit_log` action strings. No schema change — same pattern as spec 013/014.

- `session_register_changed` — fires on `UPDATE session_register` (or initial INSERT).
  - `target_id` = session_id.
  - `previous_value` = JSON `{"slider_value": <old_int_or_null>, "preset": "<old_preset_or_null>"}`.
  - `new_value` = JSON `{"slider_value": <new_int>, "preset": "<new_preset>"}`.
- `participant_register_override_set` — fires on INSERT or UPDATE of `participant_register_override`.
  - `target_id` = participant_id.
  - `previous_value` = JSON `{"slider_value": <old_int_or_null>, "preset": "<old_preset_or_null>"}` (null on first-time set).
  - `new_value` = JSON `{"slider_value": <new_int>, "preset": "<new_preset>", "session_slider_at_time": <int>}`.
- `participant_register_override_cleared` — fires on DELETE of `participant_register_override` (when explicitly cleared by the facilitator, NOT when cascade-deleted).
  - `target_id` = participant_id.
  - `previous_value` = JSON `{"slider_value": <old_int>, "preset": "<old_preset>"}`.
  - `new_value` = JSON `{"slider_value": null, "fallback_to": "session"}`.

Cascade-delete events (override row removed because the participant left or the session was deleted) do NOT emit `participant_register_override_cleared`. They are bounded by the cascade itself — emitting an event per cascaded row would flood the audit log on session delete. The session-delete event (existing) is sufficient.

**Rationale**:
- Three distinct event types let operators distinguish session-level vs override changes vs explicit clears at audit-query time without flag fields.
- Excluding cascade-deletes from the cleared event matches the spec 001 atomic-delete contract — the parent delete is the audit-visible action; child cascades are implementation detail.
- The `session_slider_at_time` field on override-set is informational — captures what the override was overriding at the moment of set, useful for retroactive audit review.

**Alternatives considered**:
- Single `register_changed` event with a `kind` discriminator field — rejected. Three distinct action strings keep the audit-log query patterns simple (operators filter by `action = 'session_register_changed'` rather than `action = 'register_changed' AND kind = 'session'`).
- Emit an event per cascaded row — rejected. Session-delete cascade can wipe many overrides at once; flooding the audit log with derivative events obscures the parent delete.

## 9. `SACP_FILLER_THRESHOLD` calibration default

**Decision**: Per-family default in the `BehavioralProfile` dict (per Decision 1). The env var `SACP_FILLER_THRESHOLD`, when set, overrides the per-family default uniformly across all families. When unset, each family's profile-default applies.

**Initial per-family thresholds**:

| Family | Default threshold | Rationale |
|---|---|---|
| anthropic | 0.60 | Observed verbosity tendency on reasoning-heavy turns; needs slightly higher threshold to avoid over-flagging legitimately structured replies |
| openai | 0.60 | Similar verbosity profile to anthropic on reasoning turns |
| gemini | 0.55 | Slightly terser baseline observed |
| groq | 0.55 | Speed-optimized models tend terser |
| ollama | 0.55 | Local models in observed deployments tend terser |
| vllm | 0.55 | Self-hosted profile mirrors ollama |

The placeholder `0.6` from spec §"Configuration (V16)" stays as the env-var-uniform override default. Operators who prefer one threshold across all families set the env var; otherwise the per-family defaults apply.

**Rationale**:
- Honors FR-003 ("MUST map each provider family to a default `SACP_FILLER_THRESHOLD` value") while preserving operator override capability via the env var.
- The split is conservative — only 0.05 difference between the two clusters. Expectation is that the per-family split tightens after Phase 3 production observation; v1 ships the spec's documented placeholder for the env-var path and the empirical split for the per-family path.

**Calibration-loop documentation**: `quickstart.md` includes a step that walks operators through observing `routing_log.shaping_score_ms` and the score distribution per family, then tuning either the env var (uniform tightening) or filing a Constitution §14.2 amendment (per-family tightening).

**Alternatives considered**:
- Single global default with no per-family variation — rejected. Spec FR-003 explicitly mandates per-family mapping.
- Per-family `SACP_FILLER_THRESHOLD_<FAMILY>` env vars — rejected. Six new env vars instead of one; the per-family overrides land in a future amendment per spec assumption.

## 10. Topology-7 forward note

**Decision**: At shaping pipeline init (called from `loop.py`'s session-start path), read `SACP_TOPOLOGY` env var. If set to `"7"`, do not initialize the filler scorer and do not register the register-preset emitter; skip silently with a one-time INFO log per session start. The three V16 validators run unconditionally per V16 contract; the gate is at the consumer, not the validator.

**Rationale**:
- V12 says spec 021 is incompatible with topology 7. The shaping pipeline MUST disable itself; the explicit env-var gate makes the topology-mismatch case observable in startup logs without forcing operators to remove `SACP_RESPONSE_SHAPING_ENABLED` configuration during topology transitions.
- Mirrors spec 014 §7's pattern exactly. One-time INFO log per session start avoids alert fatigue while remaining grep-able.
- The register-preset emitter is also skipped — in topology 7 there is no orchestrator-side prompt assembler to emit deltas into.

**`SACP_TOPOLOGY` env var status**: This var doesn't exist today. Adding it as a topology selector is out of scope for this spec — the gate-check is *aspirational* until topology 7 ships and a topology-selection mechanism exists. For now, the gate is dead code in Phase 3.

**Documentation note**: `quickstart.md` carries a forward reference ("If/when topology 7 ships, set `SACP_TOPOLOGY=7` to disable the shaping pipeline") so the gate is discoverable when relevant.

**Alternatives considered**:
- Detect topology dynamically from session participant connection types — rejected. Topology 7 doesn't exist yet; future deployment will surface its own detection mechanism.
- No gate; let the pipeline fail at runtime when no orchestrator-side hook exists — rejected. Violates V12's "silent assumption = incomplete" rule.
