# Tasks: Tool-List Freshness (Spec 017)

**Branch**: `017-tool-list-freshness`
**Status**: Implemented 2026-05-13

## T001 — V16 validators (4 new env vars)

Add 4 validator functions to `src/config/validators.py` and register them in VALIDATORS. Add 4 sections to `docs/env-vars.md`. Run `python scripts/check_env_vars.py` to verify green.

- [x] `validate_sacp_tool_refresh_poll_interval_s`
- [x] `validate_sacp_tool_refresh_timeout_s`
- [x] `validate_sacp_tool_list_max_bytes`
- [x] `validate_sacp_tool_refresh_push_enabled`
- [x] VALIDATORS tuple registration
- [x] `docs/env-vars.md` sections (4)
- [x] `python scripts/check_env_vars.py` green

## T002 — Core module: `src/orchestrator/tool_list_freshness.py`

New module implementing the in-memory registry and refresh logic.

- [x] `ParticipantToolRegistry` dataclass
- [x] `_REGISTRIES` session-scope dict
- [x] `_compute_hash`
- [x] `refresh_tool_list` (fetch, hash compare, audit emit, FR-010/FR-011)
- [x] `maybe_refresh` (poll-interval gate)
- [x] `get_tools`
- [x] `register_participant` (initial fetch + push-subscription stub)
- [x] `evict_session`

## T003 — loop.py integration

Wire `maybe_refresh` at `_assemble_and_dispatch` entry (before `assembler.assemble(...)`).

- [x] Import `maybe_refresh` and `get_tools` from `tool_list_freshness`
- [x] Call `await maybe_refresh(...)` at top of `_assemble_and_dispatch` (gated on `provider != "human"`)

## T004 — participant.py integration

Call `register_participant` after participant record persisted in `add_ai_participant`.

- [x] Import and call `register_participant` (fail-soft; must not block add_ai response)

## T005 — Tests: `tests/test_017_tool_freshness.py`

Unit tests for the core module.

- [x] Hash is order-independent
- [x] Refresh detects change -> True, audit row emitted
- [x] Refresh no change -> False, no audit row
- [x] Poll interval gate: no-op if not elapsed
- [x] Unset poll interval -> always no-op (SC-005)
- [x] FR-006 isolation: change for A has no effect on B
- [x] FR-010 size cap: list exceeding cap truncated + audit
- [x] FR-011 failure preservation: exception keeps old tools; audit refresh_failed
- [x] FR-014: invalid env var -> ValidationFailure

## T006 — Tests: `tests/test_017_loop_integration.py`

Integration tests for loop.py wiring.

- [x] After `maybe_refresh` returns True, assembler sees new tools on this turn
- [x] SC-001: staleness window bounded by poll interval
- [x] SC-004: `maybe_refresh` overhead within 50ms (mock adapter; overhead only)

## T007 — Status flip + preflights

- [x] spec.md Status -> `Implemented 2026-05-13`
- [x] 7 closeout preflights green
