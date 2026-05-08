# Contract: routing_log.reason Additions

**Branch**: `025-session-length-cap` | **Source**: spec FR-004, FR-007, FR-012, FR-013, FR-015, FR-026 | **Date**: 2026-05-07

Five new `routing_log.reason` enum entries are added by this spec. Each row corresponds to one FSM transition or cap-state mutation event. Cross-references spec 003 §FR-021 (loop FSM) and §FR-030 (per-stage timing capture).

---

## `cap_set`

**Trigger**: a successful cap update via the cap-set endpoint (FR-003, FR-004, FR-026).

**Payload** (additional fields beyond the standard `routing_log` columns):

```json
{
  "reason": "cap_set",
  "old_cap": {
    "kind": "none",
    "seconds": null,
    "turns": null
  },
  "new_cap": {
    "kind": "turns",
    "seconds": null,
    "turns": 50
  },
  "interpretation": "absolute" | "relative" | null,
  "actor_id": "fac_…",
  "current_elapsed_at_set": {
    "turns": 12,
    "seconds": 720
  }
}
```

`interpretation` is non-null only when the cap-set involved a cap-decrease that triggered the disambiguation flow (research.md §3, FR-026).

`actor_id` MUST be the facilitator's participant ID; non-facilitator attempts produce 403 before any row is written.

---

## `conclude_phase_entered`

**Trigger**: the loop's running → conclude FSM transition (FR-005, FR-007).

**Payload**:

```json
{
  "reason": "conclude_phase_entered",
  "trigger_dimension": "turns" | "time" | "both",
  "trigger_value": {
    "turns": 16,
    "seconds": 1440
  },
  "trigger_fraction": 0.80,
  "configured_cap": {
    "kind": "turns",
    "seconds": null,
    "turns": 20
  }
}
```

`trigger_dimension`:
- `'turns'` if the turn-count crossed first.
- `'time'` if elapsed-time crossed first.
- `'both'` only if both crossed in the same dispatch evaluation (rare; OR semantics fire whichever is first, but if both already past trigger fraction at evaluation time, label as `'both'`).

`configured_cap` captures the cap state at trigger time so audit can replay the decision.

---

## `conclude_phase_exited`

**Trigger**: the loop's conclude → running FSM transition via cap extension (FR-013).

**Payload**:

```json
{
  "reason": "conclude_phase_exited",
  "exit_cause": "cap_extended",
  "old_cap": { "kind": "turns", "seconds": null, "turns": 20 },
  "new_cap": { "kind": "turns", "seconds": null, "turns": 50 },
  "elapsed_at_exit": {
    "turns": 19,
    "seconds": 1710
  }
}
```

`exit_cause` is `'cap_extended'` for v1 (the only path back to running). Reserved for future causes.

`elapsed_at_exit` lets the audit reconstruct that the exit happened mid-conclude (e.g., turn 19 in a 20→50 extension scenario from US3).

---

## `auto_pause_on_cap`

**Trigger**: the loop's conclude → paused FSM transition after the final summarizer (FR-012).

**Payload**:

```json
{
  "reason": "auto_pause_on_cap",
  "summarizer_outcome": "success" | "failed_closed" | "skipped",
  "conclude_turns_produced": 3,
  "conclude_turns_skipped": 0,
  "conclude_phase_duration_seconds": 412
}
```

`conclude_turns_produced` + `conclude_turns_skipped` together MUST equal the count of active participants at conclude-phase entry; the breakdown supports forensic analysis of FR-011 skip-and-continue behavior.

`conclude_phase_duration_seconds` measures wall-clock time from `conclude_phase_started_at` to this transition.

---

## `manual_stop_during_conclude`

**Trigger**: the loop's conclude → stopped FSM transition after the final summarizer, initiated by facilitator `stop_loop` (FR-015).

**Payload**:

```json
{
  "reason": "manual_stop_during_conclude",
  "actor_id": "fac_…",
  "summarizer_outcome": "success" | "failed_closed" | "skipped",
  "conclude_turns_produced": 2,
  "conclude_turns_skipped": 0,
  "conclude_turns_pending_at_stop": 1
}
```

`conclude_turns_pending_at_stop` records how many AIs had not yet produced their conclude turn when the facilitator clicked stop — for audit insight into how complete the wrap-up was. The summarizer still runs on whatever was produced (FR-015 ALWAYS-run-summarizer-on-conclude-stop semantics, locked by clarify Q4).

---

## Enum integration

Existing `routing_log.reason` is a string column (per spec 003 §FR-021); no schema change required to add the five new values. Application-side enum / Literal type definition is updated in `src/orchestrator/types.py` (or wherever the existing reason set lives) to include:

```python
RoutingLogReason = Literal[
    # … existing values …
    'cap_set',
    'conclude_phase_entered',
    'conclude_phase_exited',
    'auto_pause_on_cap',
    'manual_stop_during_conclude',
]
```

If any existing reason value was used elsewhere with a partial subset, this list is the new authoritative superset.

---

## Test obligations

- Each of the five new reasons MUST have at least one test asserting the row is written with the documented payload shape.
- `test_025_disambiguation.py` covers `cap_set.interpretation` field for both absolute and relative paths.
- `test_025_conclude_phase.py` covers `conclude_phase_entered.trigger_dimension` for turns-only, time-only, and both-cap scenarios.
- `test_025_summarizer_trigger.py` covers `auto_pause_on_cap.conclude_turns_produced/skipped` accounting under skip-and-continue (FR-011).
- `test_025_manual_stop.py` covers `manual_stop_during_conclude.conclude_turns_pending_at_stop` accounting.
