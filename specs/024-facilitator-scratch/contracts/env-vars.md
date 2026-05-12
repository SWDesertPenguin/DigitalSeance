# Contract: New Env Vars (V16 gate)

**Spec**: [../spec.md](../spec.md) §FR-019, §FR-022 / §Configuration (V16)
**Plan**: [../plan.md](../plan.md)
**Status**: Phase 1 contract draft

Three new `SACP_*` env vars. Each MUST have a validator in `src/config/validators.py` registered in the `VALIDATORS` tuple AND a corresponding section in `docs/env-vars.md` with the six standard fields BEFORE `/speckit.tasks` is run (V16 deliverable gate).

## §1 — SACP_SCRATCH_ENABLED

- **Type**: boolean (`0` | `1`)
- **Default**: `0` (master switch ships off; operators opt in)
- **Valid range**: `0` or `1`
- **Fail-closed**: any non-parseable value MUST cause startup exit. When `0`, every scratch endpoint returns HTTP 404 and the SPA does NOT render the scratch panel entry-point button.
- **Scope**: master switch for the entire scratch feature surface.

## §2 — SACP_SCRATCH_NOTE_MAX_KB

- **Type**: positive integer (kilobytes)
- **Default**: `64`
- **Valid range**: `[1, 1024]` (1 KiB to 1 MiB)
- **Fail-closed**: outside the range MUST cause startup exit.
- **Scope**: per-note content size cap; HTTP 413 above.
- **Note**: raising past 1 MiB is unsupported in v1.

## §3 — SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE

- **Type**: positive integer, or empty for indefinite
- **Default**: empty
- **Valid range**: `[1, 36500]` when set
- **Fail-closed**: any non-integer or non-positive value MUST cause startup exit.
- **Scope**: account-scoped notes only; session-scoped notes are deleted on archive regardless.
- **Note**: the retention sweep is operator-scheduled via `scripts/scratch_retention_sweep.py`.

## Registration order in `VALIDATORS`

All three validators MUST be appended to the `VALIDATORS` tuple in `src/config/validators.py` AFTER the existing entries:

```python
validate_scratch_enabled,
validate_scratch_note_max_kb,
validate_scratch_retention_days_after_archive,
```

The `check_env_vars.py` preflight asserts the docs section count matches the `VALIDATORS` tuple count.
