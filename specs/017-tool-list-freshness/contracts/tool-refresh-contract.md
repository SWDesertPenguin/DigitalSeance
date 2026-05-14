# Contract: Tool-List Refresh

## Poll cycle contract

- `maybe_refresh(session_id, participant_id, adapter, pool)` is called at `_assemble_and_dispatch` entry for every non-human speaker.
- If `SACP_TOOL_REFRESH_POLL_INTERVAL_S` is unset, `maybe_refresh` returns False immediately (no-op; pre-feature baseline preserved).
- If the registry for `(session_id, participant_id)` does not exist (participant has no MCP server or `register_participant` was not called), `maybe_refresh` returns False.
- The poll-interval gate: `(utcnow() - last_refreshed_at).total_seconds() >= interval_s`. If not elapsed, returns False.
- If elapsed, calls `refresh_tool_list(...)` and returns its result.
- `maybe_refresh` MUST NOT raise. Any exception is caught, logged at WARNING, and False is returned (V6 graceful degradation).

## Hash comparison contract

- `_compute_hash(tools)` computes `sha256(json.dumps(sorted(tools, key=lambda t: t.get("name","")), sort_keys=True).encode()).hexdigest()`.
- Identical tool sets in different response order produce the same hash (order-independent).
- Hash comparison in `refresh_tool_list`: if `new_hash == registry.tool_set_hash`, no change: update `last_refreshed_at`, reset `consecutive_failures`, return False.
- If `new_hash != registry.tool_set_hash`, update registry, emit audit row, return True.
- The registry update and audit row write are the only side effects on change detection. The system prompt is rebuilt by the assembler on this same turn because the assembler reads `get_tools(session_id, participant_id)` which returns the freshly updated list.

## Audit emission contract

- Every call to `refresh_tool_list` that detects a change MUST emit exactly one `admin_audit_log` row per changed tool (or one row for the overall change if the diff is not tool-granular for the `schema_changed`/`description_changed` case).
- Emit one row per `change_kind` detected in the diff. For a refresh that adds one tool and removes another: two rows, one `added` and one `removed`.
- On refresh failure (`refresh_failed`): one row with `change_kind=refresh_failed`; no hash update; `consecutive_failures` incremented.
- The `facilitator_id` column uses `await pool.fetchval("SELECT facilitator_id FROM sessions WHERE id=$1", session_id)` with fallback to `participant_id` if session lookup fails.
- Audit rows are best-effort: if the INSERT fails, log the error and continue (the cached list state is authoritative; the audit row is observability).

## Isolation contract (SC-003)

- `_REGISTRIES` is keyed by `(session_id, participant_id)`. A refresh for participant A does NOT touch participant B's registry.
- Audit rows carry `target_id = participant_id`. No cross-participant leakage in the audit payload.
- `evict_session(session_id)` removes all keys where `key[0] == session_id`.
