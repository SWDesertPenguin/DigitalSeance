# Contract: New Environment Variables (V16)

**Branch**: `025-session-length-cap` | **Source**: spec FR-024, FR-025, Configuration (V16) section | **Date**: 2026-05-07

Five new `SACP_*` environment variables. Per Constitution V16, each MUST have a validator function in `src/config/validators.py` (registered in the `VALIDATORS` tuple) AND a corresponding section in `docs/env-vars.md` with the six standard fields BEFORE `/speckit.tasks` runs (FR-025 — V16 deliverable gate).

The six standard fields per `docs/env-vars.md` convention: Default, Type, Valid range, Blast radius, Validation rule, Source spec.

---

## `SACP_LENGTH_CAP_DEFAULT_KIND`

| Field | Value |
|---|---|
| **Default** | `none` |
| **Type** | string enum |
| **Valid range** | `none` \| `time` \| `turns` \| `both` |
| **Blast radius** | All new sessions inherit this default. Existing sessions are unaffected. The facilitator can override per-session at session-create. |
| **Validation rule** | `value in {'none', 'time', 'turns', 'both'}` else fail-closed exit. |
| **Source spec** | spec 025 FR-024, Configuration (V16) section |

---

## `SACP_LENGTH_CAP_DEFAULT_SECONDS`

| Field | Value |
|---|---|
| **Default** | `` (empty — no default time cap) |
| **Type** | positive integer (seconds), or empty |
| **Valid range** | `[60, 2_592_000]` (1 minute to 30 days) when set |
| **Blast radius** | New sessions with `length_cap_kind in ('time', 'both')` inherit this default. The facilitator can override per-session. |
| **Validation rule** | empty OR (parses-as-int AND `60 <= value <= 2_592_000`) else fail-closed exit. |
| **Source spec** | spec 025 FR-024, Configuration (V16) section |

---

## `SACP_LENGTH_CAP_DEFAULT_TURNS`

| Field | Value |
|---|---|
| **Default** | `` (empty — no default turn cap) |
| **Type** | positive integer, or empty |
| **Valid range** | `[1, 10_000]` when set |
| **Blast radius** | New sessions with `length_cap_kind in ('turns', 'both')` inherit this default. The facilitator can override per-session. |
| **Validation rule** | empty OR (parses-as-int AND `1 <= value <= 10_000`) else fail-closed exit. |
| **Source spec** | spec 025 FR-024, Configuration (V16) section |

---

## `SACP_CONCLUDE_PHASE_TRIGGER_FRACTION`

| Field | Value |
|---|---|
| **Default** | `0.80` |
| **Type** | float |
| **Valid range** | `(0.0, 1.0)` exclusive |
| **Blast radius** | Applies to ALL sessions (not per-session). Changes the fraction of cap consumed before conclude phase fires. Lower values trigger conclude earlier; higher values closer to 100%. |
| **Validation rule** | parses-as-float AND `0.0 < value < 1.0` else fail-closed exit. 0.0 means "always concluding"; 1.0 means "no conclude phase, hard stop only" — both pathological per spec line 386–389. |
| **Source spec** | spec 025 FR-005, Configuration (V16) section |

---

## `SACP_CONCLUDE_PHASE_PROMPT_TIER`

| Field | Value |
|---|---|
| **Default** | `4` |
| **Type** | integer |
| **Valid range** | `{1, 2, 3, 4}` (matches spec 008's tier set) |
| **Blast radius** | Applies to ALL sessions. Changes which tier the conclude delta attaches to. Default Tier 4 is the only tier reliably present (research.md §4); operators with custom tier semantics can attach earlier if they know what they're doing. |
| **Validation rule** | parses-as-int AND `value in {1, 2, 3, 4}` else fail-closed exit. |
| **Source spec** | spec 025 FR-008, Configuration (V16) section |

---

## Validator implementation pattern

All five validators follow the existing `src/config/validators.py` pattern:

```python
def validate_sacp_length_cap_default_kind() -> None:
    raw = os.environ.get("SACP_LENGTH_CAP_DEFAULT_KIND", "none")
    if raw not in {"none", "time", "turns", "both"}:
        raise ConfigValidationError(
            "SACP_LENGTH_CAP_DEFAULT_KIND",
            raw,
            "must be one of: none, time, turns, both",
        )
```

Each validator is registered in the `VALIDATORS` tuple at module bottom. Startup walks the tuple and raises before any port is bound — matches V16's "validate before binding" rule.

---

## docs/env-vars.md sections

Same five vars get sections in `docs/env-vars.md` with the same six fields (rendered as a table per existing convention in that file). The validator and the doc section MUST land together in the same task per FR-025; CI's V16 gate (per project memory and spec 012 patterns) flags any var with a validator but no doc section, and vice versa.

---

## Test obligations

- `test_025_validators.py` covers each of the five validators:
  - Valid value passes.
  - Out-of-range value raises `ConfigValidationError` with the offending var name.
  - Empty value (where allowed) passes.
  - Empty value (where not allowed — `_TRIGGER_FRACTION`, `_PROMPT_TIER`, `_DEFAULT_KIND`) uses default.
- `test_025_validators.py` covers the V16 startup gate: invalid value at startup MUST exit before binding.
- `test_025_validators.py` covers cross-var consistency: `SACP_LENGTH_CAP_DEFAULT_KIND='time'` with `SACP_LENGTH_CAP_DEFAULT_SECONDS=''` is valid (env-side default may be unset; facilitator must specify on session-create); same for `'turns'` × `_DEFAULT_TURNS=''`. The orchestrator MUST emit a startup warning (NOT an exit) if an inconsistent default leaves new sessions unable to honor the inherited `kind`.
