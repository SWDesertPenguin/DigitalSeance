# Contract: dynamic-mode-assignment SACP_* env vars

Six new vars introduced in this feature. Each lands in `src/config/validators.py` AND `docs/env-vars.md` BEFORE `/speckit.tasks` per spec FR-014 (V16 deliverable gate).

## `SACP_DMA_TURN_RATE_THRESHOLD_TPM`

- **Default**: unset (turn-rate signal does not contribute)
- **Type**: integer (turns per minute)
- **Valid range**: `1 <= value <= 600`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_dma_turn_rate_threshold_tpm`
- **Source spec(s)**: 014 §FR-003 / FR-004

## `SACP_DMA_CONVERGENCE_DERIVATIVE_THRESHOLD`

- **Default**: unset (convergence-derivative signal does not contribute)
- **Type**: float (per-window absolute derivative magnitude of similarity score)
- **Valid range**: `0.0 < value <= 1.0`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_dma_convergence_derivative_threshold`
- **Source spec(s)**: 014 §FR-003 / FR-004 (depends on spec 004 `last_similarity` hook)

## `SACP_DMA_QUEUE_DEPTH_THRESHOLD`

- **Default**: unset (queue-depth signal does not contribute)
- **Type**: integer (count of pending messages across human-side batch queues per session)
- **Valid range**: `1 <= value <= 1000`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_dma_queue_depth_threshold`
- **Source spec(s)**: 014 §FR-003 / FR-004 (soft dependency on spec-013 batching)

## `SACP_DMA_DENSITY_ANOMALY_RATE_THRESHOLD`

- **Default**: unset (density-anomaly signal does not contribute)
- **Type**: integer (count of density-anomaly-flagged turns per observation window minute)
- **Valid range**: `1 <= value <= 60`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_dma_density_anomaly_rate_threshold`
- **Source spec(s)**: 014 §FR-003 / FR-004 (sources from existing `src/orchestrator/density.py`)

## `SACP_DMA_DWELL_TIME_S`

- **Default**: unset (allowed in advisory mode; required when auto-apply is enabled)
- **Type**: integer (seconds)
- **Valid range**: `30 <= value <= 1800`
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_dma_dwell_time_s`
- **Source spec(s)**: 014 §FR-007 / FR-010
- **Cross-validator constraint**: when `SACP_AUTO_MODE_ENABLED=true` AND this is unset, V16 fails with a message naming both vars (FR-010).

## `SACP_AUTO_MODE_ENABLED`

- **Default**: `false` (advisory mode — recommendations only, no auto-toggle of spec-013 mechanisms)
- **Type**: boolean (`true` / `false`)
- **Valid range**: exactly `"true"` or `"false"` (case-sensitive)
- **Blast radius on invalid**: V16 startup validator refuses to bind ports
- **Validation rule**: `validators.validate_auto_mode_enabled`
- **Source spec(s)**: 014 §FR-006 / FR-010 / FR-011
- **Note**: setting this to `true` requires prior advisory-mode validation per spec User Story priority ordering (Story 1 P1 → Story 2 P2). The `docs/env-vars.md` entry MUST call out this operator-trust prerequisite.

## CI-gate alignment

Per spec 012 FR-005 the `scripts/check_env_vars.py` gate scans `src/` for `os.environ.get("SACP_*")` calls and asserts each has a section in `docs/env-vars.md`. The six vars above MUST satisfy that gate before `/speckit.tasks` is run.

The validators MUST also be appended to the `VALIDATORS` tuple in `src/config/validators.py` so they fire during `validate_all()` at orchestrator startup (V16 contract). The `validate_auto_mode_enabled` validator MUST cross-check `SACP_DMA_DWELL_TIME_S` for the FR-010 dependency (a single validator that returns failure when auto-apply is on without dwell).
