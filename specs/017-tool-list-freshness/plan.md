# Implementation Plan: Tool-List Freshness for Participant-Registered MCP Servers

**Branch**: `017-tool-list-freshness` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/017-tool-list-freshness/spec.md`

## Summary

Per-participant polling-based tool-list freshness for participant-registered MCP servers. Each participant's cached tool registry is checked at the §4.2 turn-prep boundary (`_assemble_and_dispatch` entry in loop.py); when the registry's hash differs from the last-known hash, the system prompt is rebuilt on this turn with the fresh tool set and a `tool_list_changed` audit row lands in `admin_audit_log`. Push subscription stubs ship gated by `SACP_TOOL_REFRESH_PUSH_ENABLED=false`. No schema changes — all audit rows reuse the existing `admin_audit_log` table; the `ParticipantToolRegistry` is in-memory per session.

## Technical Context

**Language/Version**: Python 3.14.4 (per Constitution §6.8 slim-bookworm)
**Primary Dependencies**: FastAPI, asyncpg, alembic, pydantic, pytest. No new runtime dependencies. The MCP tool-list fetch uses the existing LiteLLM/MCP adapter path (or a direct HTTP call to the participant's registered MCP server URL).
**Storage**: PostgreSQL 16. No schema changes. `tool_list_changed` audit events go to the existing `admin_audit_log` table (same pattern as spec 013/014/021/022). In-memory `ParticipantToolRegistry` per `(session_id, participant_id)` key; not persisted across restart.
**Testing**: pytest
**Target Platform**: Linux server (Docker, slim-bookworm)
**Project Type**: Single project
**Performance Goals**: Hash check at turn-prep boundary: O(1) (hash comparison, no re-fetch). Poll refresh: async, out-of-band from turn loop, captured in audit entry. System-prompt rebuild on change: within V14 50ms orchestrator overhead budget.
**Constraints**: V14 turn-prep budget (50ms overhead). All four `SACP_TOOL_*` env vars must be documented and validated BEFORE `/speckit.tasks` runs (V16 gate).
**Scale/Scope**: Per-session, per-participant in-memory registry. Polling cadence shared across all participants in v1 (per-participant override is a follow-up).

## Constitution Check

- **V1 (sovereignty)**: Tool registry is participant-private (FR-006). Per-participant isolation enforced by `(session_id, participant_id)` registry key. SC-003 contract test asserts zero cross-participant bleed.
- **V5 (transparency)**: Every tool-set change audited per FR-004. Subscription outcome audited per FR-007.
- **V6 (graceful degradation)**: Refresh failure preserves cached list (FR-011). `maybe_refresh` exceptions swallowed per V6; turn loop continues.
- **V14 (performance budgets)**: Hash check is O(1). Refresh is async/out-of-band from the turn loop dispatch. SC-004 contract test measures per-turn overhead.
- **V16 (env var gates)**: 4 validators, 4 env-var sections in `docs/env-vars.md`, registered in VALIDATORS tuple.

## Project Structure

### Documentation (this feature)

```text
specs/017-tool-list-freshness/
+-- plan.md              (this file)
+-- research.md
+-- data-model.md
+-- quickstart.md
+-- contracts/
|   +-- tool-refresh-contract.md
+-- tasks.md
```

### Source Code (repository root)

```text
src/
+-- orchestrator/
|   +-- tool_list_freshness.py   (new module: registry, hash, poll/refresh)
|   +-- loop.py                  (maybe_refresh wired at _assemble_and_dispatch entry)
+-- mcp_server/
|   +-- tools/
|       +-- participant.py       (register_participant called at add_ai_participant)
+-- config/
    +-- validators.py            (4 new validators + VALIDATORS registration)

docs/
+-- env-vars.md                  (4 new sections)

tests/
+-- test_017_tool_freshness.py
+-- test_017_loop_integration.py
```

**Structure Decision**: Single project. No new tables, no new files outside these paths.

## Complexity Tracking

No constitution violations. All added complexity serves required spec behavior.
