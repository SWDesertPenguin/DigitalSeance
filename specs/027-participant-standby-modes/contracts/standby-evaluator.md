# Contract: StandbyEvaluator

**Module**: `src/orchestrator/standby.py`

## Public surface

```python
class StandbyEvaluator:
    """Per-tick evaluator that transitions participants in/out of standby."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        encryption_key: str,
        filler_detection_turns: int,
        pivot_timeout_seconds: int,
        pivot_rate_cap: int,
    ) -> None: ...

    async def evaluate_tick(
        self,
        session_id: str,
        current_turn: int,
    ) -> StandbyEvalResult: ...
```

The evaluator runs in the round-robin tick path BEFORE the router picks the next speaker. It produces a `StandbyEvalResult` carrying:

- `entered`: list of `(participant_id, reason)` pairs that transitioned INTO standby this tick.
- `exited`: list of `participant_id` that transitioned OUT of standby this tick.
- `observer_marked`: list of `participant_id` that transitioned to long-term-observer this tick.
- `pivot_message_text`: optional str. Non-None when the pivot evaluator fired AND the rate-cap allowed the injection.

The caller (`loop.py`) consumes the result by:

1. Updating the round-robin skip-set per the entered/exited lists.
2. Writing the audit-log rows + emitting the WS events per the entered/exited/observer_marked lists.
3. Persisting the pivot message + audit row when `pivot_message_text is not None`.

## Pre-conditions

- The session is not paused (the standby evaluator does not run during a paused loop — checked by the caller before invocation).
- The four V16 env vars passed in __init__ are validated (validator family asserts at startup).

## Post-conditions

- The participant rows for any entered/exited/observer_marked participants have been UPDATEd.
- The `standby_cycle_count` for each currently-standby participant has been incremented by exactly 1 on this tick (whether they transitioned this tick or were already standby).
- The result object is the SOLE source-of-truth for the caller's downstream side-effects.

## Performance budget

- O(1) per participant per tick.
- P95 < 1ms per participant (V14, instrumented as `routing_log.standby_eval_ms`).

## Detection signal contracts

Each of the four signals is a pure async function returning `bool`:

```python
async def _signal_unresolved_question(...) -> bool
async def _signal_pending_review_gate(...) -> bool
async def _signal_proposal_awaiting_vote_with_filler(...) -> bool
async def _signal_filler_stuck(...) -> bool  # FR-007, reads routing_log.filler_score
```

The evaluator's main loop walks each `wait_mode='wait_for_human'` participant, calls each signal in order, short-circuits on the FIRST true return, and records the triggering signal name in the audit row's metadata.

The signal-#4 evaluator skips its check when a `density_anomaly` `routing_log` row exists for the same participant + same tick (FR-007 off-rails coordination with spec 014).

## Failure mode

If any signal evaluator raises, the evaluator catches the exception, writes a `routing_log` row with `reason='standby_eval_error'` for the affected participant, and skips standby evaluation for THAT participant THIS tick. Other participants continue evaluation normally. The loop does NOT halt on standby-eval failure (V6 graceful degradation).
