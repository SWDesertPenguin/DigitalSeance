# Contract: high-traffic-mode SACP_* env vars

Three new vars introduced in this feature. Each lands in `src/config/validators.py` AND `docs/env-vars.md` BEFORE `/speckit.tasks` per spec FR-014 (V16 deliverable gate).

## `SACP_HIGH_TRAFFIC_BATCH_CADENCE_S`

- **Default**: unset (per-turn delivery, current Phase 2 behavior)
- **Type**: positive integer (seconds)
- **Valid range**: `1 <= value <= 300` (1 second to 5 minutes)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_high_traffic_batch_cadence_s`
- **Source spec(s)**: 013 §FR-001 / FR-003 / SC-002

## `SACP_CONVERGENCE_THRESHOLD_OVERRIDE`

- **Default**: unset (use global `SACP_CONVERGENCE_THRESHOLD` from spec 004)
- **Type**: float
- **Valid range**: `0.0 < value < 1.0` (strict bounds — `0.0` and `1.0` are operator-error states per spec 004 line 111)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_convergence_threshold_override`
- **Source spec(s)**: 013 §FR-005 / FR-007

## `SACP_OBSERVER_DOWNGRADE_THRESHOLDS`

- **Default**: unset (no downgrades; current Phase 2 behavior)
- **Type**: composite key:value string (`participants:N,tpm:N,restore_window_s:N`)
- **Valid range**:
  - `participants` — required; integer in `[2, 10]`
  - `tpm` — required; integer in `[1, 600]`
  - `restore_window_s` — optional; integer in `[1, 3600]`; default `120`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports (unparseable; missing required key; unknown key; out-of-range integer)
- **Validation rule**: `validators.validate_observer_downgrade_thresholds`
- **Source spec(s)**: 013 §FR-008 / FR-009 / FR-010 / FR-011

## CI-gate alignment

Per spec 012 FR-005 the `scripts/check_env_vars.py` gate scans `src/` for `os.environ.get("SACP_*")` calls and asserts each has a section in `docs/env-vars.md`. The three vars above MUST satisfy that gate before `/speckit.tasks` is run.

The validators MUST also be appended to the `VALIDATORS` tuple in `src/config/validators.py` so they fire during `validate_all()` at orchestrator startup (V16 contract).
