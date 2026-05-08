# Phase 1 Data Model: AI Response Shaping

## Module-level frozen entities

### `BehavioralProfile`

Per-provider-family profile holding the filler-scorer configuration. Frozen dataclass instances live in a module-level dict in `src/orchestrator/shaping.py`.

| Field | Type | Notes |
|---|---|---|
| `default_threshold` | `float` | Per-family default for `SACP_FILLER_THRESHOLD` when env var is unset. In `[0.0, 1.0]`. Per [research.md §9](./research.md): anthropic/openai `0.60`; gemini/groq/ollama/vllm `0.55`. |
| `hedge_weight` | `float` | Default `0.5` per FR-002. |
| `restatement_weight` | `float` | Default `0.3` per FR-002. |
| `closing_weight` | `float` | Default `0.2` per FR-002. |
| `retry_delta_text` | `str` | Tightened Tier 4 delta inserted on retry. v1 ships the Direct preset's text uniformly across all families per spec assumption. |

Lookup keys (six families enumerated in FR-003): `anthropic`, `openai`, `gemini`, `groq`, `ollama`, `vllm`.

Lifetime: module-level constant; loaded at process start; immutable thereafter.

### `RegisterPreset`

Frozen 1-5 mapping from slider value to preset metadata. Lives as a module-level tuple-of-dataclasses in `src/prompts/register_presets.py`.

| Slider | Preset name | Tier 4 delta text (per FR-013) |
|---|---|---|
| 1 | `direct` | "Reply briefly and directly. No preamble, no restatement, no closing." |
| 2 | `conversational` | "Reply in a conversational register. Brief preamble acceptable; avoid academic register." |
| 3 | `balanced` | (no delta — tier text alone) |
| 4 | `technical` | "Use precise technical register. Cite sources for non-obvious claims." |
| 5 | `academic` | "Use formal academic register. Structured argumentation with explicit citations expected." |

Lifetime: module-level constant; loaded at process start; immutable thereafter.

## DB-persistent entities

### `session_register`

One row per session holding the session-level slider value. Created on first facilitator slider-set; subsequent sets UPDATE in place.

| Column | Type | Notes |
|---|---|---|
| `session_id` | `UUID` | PK; FK to `sessions(id)` `ON DELETE CASCADE`. |
| `slider_value` | `INTEGER` | NOT NULL; `CHECK (slider_value BETWEEN 1 AND 5)`. |
| `set_by_facilitator_id` | `UUID` | NOT NULL; FK to `facilitators(id)`. |
| `last_changed_at` | `TIMESTAMPTZ` | NOT NULL; default `NOW()`. |

When no row exists for a session, the resolver falls back to `SACP_REGISTER_DEFAULT` and reports `register_source='session'` per FR-010.

### `participant_register_override`

Zero-or-one row per participant holding a per-participant override of the session slider. Created on first facilitator override-set; subsequent sets UPDATE in place; explicit clear is a DELETE.

| Column | Type | Notes |
|---|---|---|
| `participant_id` | `UUID` | PK; FK to `participants(id)` `ON DELETE CASCADE`. |
| `session_id` | `UUID` | NOT NULL; FK to `sessions(id)` `ON DELETE CASCADE`. |
| `slider_value` | `INTEGER` | NOT NULL; `CHECK (slider_value BETWEEN 1 AND 5)`. |
| `set_by_facilitator_id` | `UUID` | NOT NULL; FK to `facilitators(id)`. |
| `last_changed_at` | `TIMESTAMPTZ` | NOT NULL; default `NOW()`. |

Index: `participant_register_override_session_idx ON (session_id)` to support session-scoped queries (list-overrides-in-session).

Cascade contract per FR-015 / SC-007: row vanishes on participant delete OR on session delete. No orphan rows.

### `routing_log` extension

Two new per-stage timing columns per V14 / FR-011:

| Column | Type | Notes |
|---|---|---|
| `shaping_score_ms` | `INTEGER` | Wall-clock cost of one filler-scorer evaluation. Populated per evaluation (original draft + each retry). |
| `shaping_retry_dispatch_ms` | `INTEGER` | Wall-clock cost of one shaping-retry dispatch (provider call). Populated per retry firing only. NULL for the original draft's row. |

Plus three columns capturing the shaping decision itself per FR-011:

| Column | Type | Notes |
|---|---|---|
| `filler_score` | `NUMERIC(4,3)` | The aggregate filler score in `[0.0, 1.0]`. Populated on every dispatched draft when shaping is enabled. |
| `shaping_retry_delta_text` | `TEXT` | The tightened delta string used on this retry (NULL on the original draft's row). |
| `shaping_reason` | `TEXT` | One of `null` (no retry fired), `'filler_retry'` (retry below-threshold accepted), `'filler_retry_exhausted'` (both retries above threshold), `'shaping_pipeline_error'` (fail-closed path). |

## Transient (in-memory) entities

### `FillerScore`

Pure-function output from `compute_filler_score(draft, profile, engine) -> FillerScore`. Not persisted as a standalone entity; its fields surface as `routing_log` columns.

| Field | Type | Notes |
|---|---|---|
| `aggregate` | `float` | Weighted sum of three signals; in `[0.0, 1.0]`. |
| `hedge_signal` | `float` | Hedge-to-content ratio; in `[0.0, 1.0]`. |
| `restatement_signal` | `float` | Max cosine similarity vs prior 1-3 turns' embeddings; in `[0.0, 1.0]`. |
| `closing_signal` | `float` | Capped closing-pattern match count; in `[0.0, 1.0]`. |
| `evaluated_at` | `datetime` | Timestamp; informational. |

### `ShapingDecision`

Per-turn record of how the shaping pipeline disposed of one dispatched response. Held in memory until logged; not a standalone entity beyond the `routing_log` row(s) it produces.

| Field | Type | Notes |
|---|---|---|
| `original_score` | `FillerScore` | Score of the first dispatched draft. |
| `retries_fired` | `int` | 0, 1, or 2. |
| `retry_scores` | `list[FillerScore]` | Length matches `retries_fired`. |
| `persisted_index` | `int` | 0 (original), 1 (first retry), or 2 (second retry); points into `[original, *retries]`. |
| `exhausted` | `bool` | True iff both retries fired and both exceeded threshold. Drives `shaping_reason='filler_retry_exhausted'`. |

## DB-persistent audit shapes

Three new `admin_audit_log` `action` strings — no schema change. Same pattern as spec 013/014.

### `session_register_changed`

Fires on INSERT or UPDATE of `session_register` (i.e., facilitator sets the session-level slider).

- `target_id` — session_id.
- `previous_value` — JSON: `{"slider_value": <old_int_or_null>, "preset": "<old_preset_or_null>"}` (null on first-time set).
- `new_value` — JSON: `{"slider_value": <new_int>, "preset": "<new_preset>"}`.

### `participant_register_override_set`

Fires on INSERT or UPDATE of `participant_register_override` (facilitator sets a per-participant override).

- `target_id` — participant_id (the audit row's subject is the participant; the session is captured in the row's standard `session_id` column).
- `previous_value` — JSON: `{"slider_value": <old_int_or_null>, "preset": "<old_preset_or_null>"}` (null on first-time set).
- `new_value` — JSON: `{"slider_value": <new_int>, "preset": "<new_preset>", "session_slider_at_time": <int>}`.

### `participant_register_override_cleared`

Fires on explicit DELETE of `participant_register_override` (facilitator clears an override). Does NOT fire on cascade-delete (per [research.md §8](./research.md)).

- `target_id` — participant_id.
- `previous_value` — JSON: `{"slider_value": <old_int>, "preset": "<old_preset>"}`.
- `new_value` — JSON: `{"slider_value": null, "fallback_to": "session"}`.

## Validation rules (per V16)

Three new env vars, all validated at startup; invalid values exit before binding ports.

| Var | Validator | Failure modes |
|---|---|---|
| `SACP_FILLER_THRESHOLD` | `validate_filler_threshold` | non-float; `< 0.0`; `> 1.0`. |
| `SACP_REGISTER_DEFAULT` | `validate_register_default` | non-integer; `< 1`; `> 5`. |
| `SACP_RESPONSE_SHAPING_ENABLED` | `validate_response_shaping_enabled` | not in `{true, false}` (case-insensitive) and not in `{0, 1}`. |

## State transitions

### Filler-score evaluation per dispatched draft

```text
                ┌──────────────────────────────────────────┐
                │  draft returned from provider dispatch   │
                └─────────────────┬────────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
   shaping enabled                              shaping disabled
              │                                       │
              ▼                                       ▼
   ┌─────────────────────┐                    ┌──────────────────────┐
   │ compute_filler_     │                    │ persist draft as-is  │
   │ score(draft, ...)   │                    │ no routing-log       │
   └────────┬────────────┘                    │ shaping columns      │
            │                                  └──────────────────────┘
            ▼
   ┌─────────────────────┐    score < threshold
   │ compare to threshold├─────────────────────► persist draft; log
   └────────┬────────────┘                       routing_log row with
            │ score >= threshold                 filler_score; no retry
            ▼
   ┌──────────────────────┐    retries == 2
   │ retries_fired ?      │    OR compound
   └────────┬─────────────┤    budget exhausted
            │ < cap and    ├─────────────► persist most recent draft;
            │ budget left  │               log shaping_reason=
            ▼              │               'filler_retry_exhausted'
   ┌──────────────────────┐
   │ dispatch retry with   │
   │ tightened-delta;      │
   │ increment retries;    │
   │ recompute score       │
   └────────┬─────────────┘
            │
            └────► loop back to compare-to-threshold
```

### Register-resolution at `/me` query time

```text
   ┌─────────────────────────────────────────────────────┐
   │ /me query for participant P in session S            │
   └────────────────────────────┬────────────────────────┘
                                │
                                ▼
   ┌─────────────────────────────────────────────────────┐
   │ SELECT COALESCE(                                    │
   │   override.slider_value,                            │
   │   session.slider_value,                             │
   │   <SACP_REGISTER_DEFAULT>) AS resolved_slider,      │
   │   CASE WHEN override.slider_value IS NOT NULL       │
   │        THEN 'participant_override'                  │
   │        ELSE 'session' END AS resolved_source        │
   │ FROM participants p                                 │
   │ LEFT JOIN participant_register_override override    │
   │        ON p.id = override.participant_id            │
   │ LEFT JOIN session_register session                  │
   │        ON p.session_id = session.session_id         │
   │ WHERE p.id = $1                                     │
   └─────────────────────────────────────────────────────┘
                                │
                                ▼
   ┌─────────────────────────────────────────────────────┐
   │ /me payload extends with:                           │
   │   register_slider:  resolved_slider                  │
   │   register_preset:  preset_for(resolved_slider)      │
   │   register_source:  resolved_source                  │
   └─────────────────────────────────────────────────────┘
```

### Override row lifecycle

```text
   [no override]  ──── facilitator sets override ──→  [override active]
                                                           │
                                                           │ facilitator
                                                           │ updates override
                                                           ▼
                                                     [override active]
                                                     (slider_value updated)
                                                           │
                                          ┌────────────────┼────────────────┐
                                          │                │                │
                            facilitator clears   participant deleted   session deleted
                                          │                │                │
                                          ▼                ▼                ▼
                                   [no override]   [no override]    [no override]
                                   (audit row     (cascade,         (cascade,
                                    emitted)      no audit row)     no audit row)
```

## Persistence boundary

In-memory: `BehavioralProfile`, `RegisterPreset`, `FillerScore`, `ShapingDecision`. No DB writes from the scorer's hot path.

Persistent:
- Two new tables (`session_register`, `participant_register_override`).
- Five new `routing_log` columns (`shaping_score_ms`, `shaping_retry_dispatch_ms`, `filler_score`, `shaping_retry_delta_text`, `shaping_reason`).
- Three new `admin_audit_log` action strings (no schema change).

`routing_log` instrumentation (per V14): per-evaluation `shaping_score_ms` plus per-retry `shaping_retry_dispatch_ms`. Reuses the existing `@with_stage_timing` decorator pattern from spec 003.

## Hooks introduced

- **Spec 004 amendment** (minimal): `ConvergenceEngine.last_embedding` property + `recent_embeddings(depth)` helper, populated from a `_recent_embeddings: deque[bytes]` ring buffer of `maxlen=3`. Single-point change at `convergence.py:177`. Per [research.md §2](./research.md). Does not change spec-004 behavior.
- **Spec 008 extension**: `assemble_prompt` accepts an optional `register_delta_text` and an optional `shaping_retry_delta_text` parameter. Both are appended after the existing tier text (and after any participant custom prompt). Order: tier text → custom_prompt → register_delta → shaping_retry_delta (the retry delta sits closest to the user turn so it dominates the model's attention). The canary embedding still wraps the assembled output.
- **Spec 003 extension** (`routing_log`): five new columns per FR-011. Migration adds them with `DEFAULT NULL` to preserve backward compatibility for any in-flight rows.
- **Spec 001 extension** (`/me` payload): three additive top-level fields per FR-010. Backward-compatible — existing clients ignore unknown fields.
