# Contract: Cap-Set Endpoint

**Branch**: `025-session-length-cap` | **Source**: spec FR-003, FR-016, FR-020..FR-022, FR-026 | **Date**: 2026-05-07

Defines the HTTP and MCP shapes for setting/updating per-session length caps. Cross-references the disambiguation flow from research.md §3.

---

## HTTP Endpoint

**Path**: `PATCH /api/sessions/{session_id}/settings` (extends spec 006's existing session-settings endpoint per research.md §2; no new resource path)

**Authentication**: facilitator session token (mirrors spec 006 §FR-007). Non-facilitators receive HTTP 403 with body `{"error": "facilitator_only"}` per FR-016.

### Request body

```json
{
  "length_cap_kind": "none" | "time" | "turns" | "both",
  "length_cap_seconds": 1800,
  "length_cap_turns": 20,
  "interpretation": "absolute" | "relative" | null
}
```

All four fields optional in any combination. Fields not present in the request preserve their current value (PATCH semantics). The `interpretation` field is only meaningful when the request would decrease the cap below current elapsed (see Disambiguation flow below).

### Validation

Per FR-020, FR-021, FR-022:

| Rule | Error | HTTP code |
|---|---|---|
| `length_cap_seconds` outside `[60, 2_592_000]` (1 min – 30 days) | `length_cap_seconds_out_of_range` | 422 |
| `length_cap_turns` outside `[1, 10_000]` | `length_cap_turns_out_of_range` | 422 |
| Both `length_cap_seconds` and `length_cap_turns` zero or negative | `length_cap_invalid_zero_or_negative` | 422 |
| `length_cap_kind='time'` but `length_cap_seconds` is null | `length_cap_kind_time_requires_seconds` | 422 |
| `length_cap_kind='turns'` but `length_cap_turns` is null | `length_cap_kind_turns_requires_turns` | 422 |
| `length_cap_kind='both'` but either `seconds` or `turns` null | `length_cap_kind_both_requires_both` | 422 |
| `length_cap_kind='none'` but either `seconds` or `turns` non-null | `length_cap_kind_none_forbids_values` | 422 |
| `interpretation` set but submitted value not below current elapsed | `interpretation_only_for_cap_decrease` | 422 |

### 200 OK response

Returned when the cap change is committed cleanly (no disambiguation required). Body:

```json
{
  "session_id": "ses_…",
  "length_cap_kind": "turns",
  "length_cap_seconds": null,
  "length_cap_turns": 50,
  "current_elapsed": {"turns": 12, "seconds": 720},
  "trigger_threshold": {"turns": 40, "seconds": null},
  "phase": "running"
}
```

`trigger_threshold` is the trigger-fraction × cap value where conclude phase will fire. `phase` is the current loop state after the cap change (typically `running`; see Disambiguation flow for cases where the cap-set itself causes a transition).

### 409 Disambiguation response

Returned when the submitted cap is below the current elapsed counter on the relevant dimension AND `interpretation` is not present in the request. Body:

```json
{
  "error": "cap_decrease_requires_interpretation",
  "current_elapsed": {"turns": 30, "seconds": null},
  "submitted": {"length_cap_turns": 20},
  "options": {
    "absolute": {
      "effective_cap_turns": 20,
      "consequence": "immediate_conclude_phase",
      "description": "Loop transitions to conclude phase on the next dispatch; runs one round of conclude turns; final summarizer fires; loop pauses with reason='auto_pause_on_cap'."
    },
    "relative": {
      "effective_cap_turns": 50,
      "consequence": "loop_continues_until_trigger",
      "description": "Submitted value treated as 20 additional turns beyond current elapsed (effective cap = 30 + 20 = 50). Loop continues; conclude phase triggers when elapsed crosses trigger fraction (40 turns at 0.80)."
    }
  }
}
```

The frontend renders both options as a modal; the facilitator picks one; the client re-POSTs with `interpretation` set. The orchestrator commits the chosen interpretation and returns 200. Both the request and the resulting `routing_log.cap_set` row preserve the `interpretation` field for the audit trail.

### Side effects

On 200 success:
- `sessions.length_cap_*` columns updated atomically.
- One row appended to `routing_log` with `reason='cap_set'` carrying old + new values + `interpretation` (or null).
- If the new cap (under the chosen interpretation) places current elapsed at or above the trigger fraction, the loop transitions to conclude phase on the NEXT dispatch (NOT inline in this request) — emitted as a separate `routing_log.conclude_phase_entered` row at that time.
- WS event NOT broadcast on cap-set itself; broadcast only on phase transitions.

---

## MCP Tool Variant

The MCP server exposes a tool with the same shape and same authorization. Tool name: `update_session_length_cap`. Tool arguments mirror the HTTP request body. MCP responses use the same shape; the 409 disambiguation response surfaces as a structured tool error with the `options` payload preserved.

```json
{
  "name": "update_session_length_cap",
  "arguments": {
    "session_id": "ses_…",
    "length_cap_kind": "turns",
    "length_cap_turns": 50
  }
}
```

Cross-ref `src/mcp_server/tools.py` for registration. The tool's underlying implementation calls the same `length_cap.detect_decrease_intent()` helper as the HTTP endpoint (research.md §7), so disambiguation behavior is transport-agnostic.

---

## Test obligations

Per spec.md SC-002/SC-003/SC-009:

- `test_025_disambiguation.py` covers: 409 returned on cap-decrease without `interpretation`; 200 returned on cap-decrease with explicit `absolute` or `relative`; 422 returned on `interpretation` set without a decrease.
- `test_025_disambiguation.py` also covers the MCP tool variant returning the same `options` payload.
- `test_025_validators.py` covers the 8 FR-020/021/022 422 paths.
- Auth path: 403 on non-facilitator (mirrors spec 006 test pattern).
