# Research: Provider Failure Detection and Isolation (Bridge-Layer Circuit Breaker)

**Branch**: `015-provider-failure-detection` | **Date**: 2026-05-13 | **Plan**: [plan.md](./plan.md)

Resolves the six open decisions queued in [plan.md §"Phase 0 — Outline & Research"](./plan.md). Each section answers one question and closes with Decision / Rationale / Alternatives.

---

## §1 — State machine design: three-state vs two-state

**Decision**: three-state machine — `closed` / `open` / `half_open`.

**Rationale**: The spec's FR-006 says "at most one probe per backoff tick per breaker." A two-state (`open` / `closed`) machine would either (a) admit the probe while remaining `open`, making the breaker's observable state ambiguous during probing, or (b) transition to `closed` optimistically on probe issuance, losing the signal on probe failure. The `half_open` intermediate state makes the probing window explicit: the breaker enters `half_open` when the next backoff interval elapses, admits exactly one dispatch (the probe), and transitions to `closed` on success or back to `open` on failure. This gives operators a third distinct observable value in the metrics surface (US3 FR-013) without adding complexity to the normal dispatch hot path — `is_open()` returns `True` for both `open` and `half_open`, and the probe call itself is the only `half_open` action.

**Alternatives considered**:
- **Two-state (open/closed)**: simpler implementation; loses observable `half_open` state visible in US3 metrics; making probe scheduling purely time-based without a state guard risks issuing probes before the backoff interval elapses on every dispatch turn. Rejected — spec FR-006 constraint and US3 metrics requirement favor three-state.
- **Four-state (adding a `probe_in_flight` state)**: avoids concurrent probe issuance across async coroutines but introduces locking complexity. The per-session in-memory model already provides single-writer semantics through asyncio's cooperative scheduler; the `half_open` state with an `active_probe_task` flag on `CircuitState` is sufficient. Rejected as over-engineering.

---

## §2 — Sliding window implementation: ring buffer vs time-bucketed counters

**Decision**: ring buffer of `(timestamp, failure_kind)` entries, trim-on-read, bounded by `max(SACP_PROVIDER_FAILURE_THRESHOLD * 4, 20)` entries.

**Rationale**: The spec defines `FailureRecord` as a ring buffer explicitly (spec §"Key Entities"). The ring buffer keeps full per-event timestamps and failure_kind values, supporting FR-013's trigger-reason breakdown (errors / timeouts / quality / auth / rate_limit) without a secondary structure. Trim-on-read (discard entries older than `SACP_PROVIDER_FAILURE_WINDOW_S` before counting) ensures the window is always accurate at check time. The size bound prevents unbounded growth even for long-running sessions with sustained failure rates — `threshold * 4` ensures the buffer never fills before the oldest entries age out at normal failure rates, and the 20-entry floor handles very small threshold values. Python `collections.deque(maxlen=N)` provides O(1) append and left-truncation; the trim-on-read pass iterates from the left until entries are in-window, also O(entries trimmed) amortized O(1).

**Alternatives considered**:
- **Time-bucketed counters (e.g., one integer per second)**: lower per-entry memory; constant-time read. Loses the `failure_kind` breakdown needed for FR-013 trigger-reason metrics. Requires a different secondary structure for the breakdown. Rejected.
- **Simple Python list with manual index**: equivalent to deque but without the maxlen guard. Deque is preferred.
- **Database-backed ring buffer**: allows persistence across restarts; inconsistent with spec §Assumptions ("session-local circuit-state model; not persisted across restart"). The audit tables are the persistence story; in-memory ring buffer is the hot-path implementation. Rejected.

---

## §3 — Probe design: full dispatch vs validate_credentials

**Decision**: `adapter.validate_credentials(api_key, model)` call, not a full `adapter.dispatch()` call.

**Rationale**: FR-007 requires "a minimal-cost call that does not enter the conversation transcript." `ProviderAdapter.validate_credentials()` is already defined in the ABC (`src/api_bridge/adapter.py`) and is the same lightweight credential-check call used by the existing `update_api_key` MCP tool path (spec §7.1). It takes only `api_key` and `model` — no message list, no token spend, no transcript write. A full `dispatch()` call would require constructing a synthetic message list, would consume tokens, and would produce a response that must be silently discarded without entering the messages table — violating FR-007's "do not enter the transcript" requirement. The `validate_credentials()` path satisfies FR-007 with zero implementation complexity beyond scheduling.

The probe timeout (`SACP_PROVIDER_PROBE_TIMEOUT_S`) wraps the `validate_credentials()` call with an `asyncio.wait_for()` guard. A timeout on the probe counts as a failed probe (conservative: keep breaker open) and preserves the backoff schedule position per spec FR-006.

**Alternatives considered**:
- **Full LiteLLM dispatch with a minimal prompt**: token-burning, transcript-polluting. Rejected per FR-007.
- **HTTP HEAD request to the provider's endpoint**: provider-specific; LiteLLM adapts many providers that don't expose a HEAD endpoint at their API base URL. The `validate_credentials()` abstraction already handles provider-specific probe mechanics. Rejected.

---

## §4 — Backoff schedule parsing and cycle semantics

**Decision**: parse at startup (V16 validator); `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF` is a comma-separated list of positive integers (seconds); each entry validated in `[1, 600]`; 1-10 entries; cycle-on-last-value when the schedule exhausts.

**Parsing**: the validator splits on commas, strips whitespace, rejects empty entries, parses each entry as int, validates the range, and validates the entry count. A parsed `tuple[int, ...]` is cached for the session's probe scheduler. Parsing at startup satisfies V16 fail-closed semantics — a bad value exits at startup, not mid-session.

**Cycle-on-last**: FR-009 says "when the schedule exhausts, loop on its longest interval." The last entry in the user-supplied list is taken as the longest interval (users are expected to supply an increasing sequence; no sort enforcement to preserve user intent). When `probe_schedule_position >= len(schedule)`, the position stays pinned at `len(schedule) - 1` and that interval repeats. A single audit entry is emitted per exhaustion cycle (i.e., once per loop-around at the last position, not on every repeated probe) per FR-009.

**Alternatives considered**:
- **Parse at first use**: defers the error until a breaker trips, which may be hours into a session. Rejected per V16.
- **Sort and validate ascending**: enforcing an ascending sequence would reject valid operator choices (e.g., `10,5,10` for a deliberate non-monotone schedule). Rejected — user intent preserved.
- **Unbounded growth (multiply last by 2 on each exhaustion)**: spec FR-009 explicitly rejects unbounded growth. Rejected.

---

## §5 — Integration with loop.py dispatch sequence

**Decision**: two call sites in the existing loop, extended to pass the full FR-001 key tuple.

**Check site** (`_check_skip_conditions` in `loop.py`): add `await breaker.is_open(session_id, participant_id, provider, api_key_fingerprint)` alongside the existing budget check. Returns True for both `open` and `half_open` states (dispatch skipped). `half_open` is the exception: when the backoff interval has elapsed and the breaker is in `half_open`, a single probe call is issued out-of-band (via `asyncio.create_task`) and the turn is still skipped; the probe result transitions the breaker asynchronously.

**Failure site** (`_record_failure_and_announce` in `loop.py`): replace the existing `await breaker.record_failure(speaker.id)` call with `await breaker.record_failure(session_id, participant_id, provider, api_key_fingerprint, failure_kind)`. The `failure_kind` is derived from the `CanonicalErrorCategory` of the dispatch exception via `adapter.normalize_error(exc)`.

**Key tuple threading**: `speaker` (participant object) already carries `provider` and `api_key_encrypted`. The `api_key_fingerprint` is computed as the first 8 characters of the hex-encoded SHA-256 of the encrypted key — sufficient for per-key isolation without storing the key in the circuit state. The `session_id` is already on the `_TurnContext` object threaded through the dispatch path. No new parameters need to be added to `_check_skip_conditions` or `_record_failure_and_announce` beyond what already flows through `ctx` and `speaker`.

**Probe scheduling**: probes run as `asyncio.create_task` calls inside the breaker, not inside the turn loop. This satisfies V14's "probes MUST NOT block dispatch for any other participant." The breaker maintains a per-circuit `_probe_task: asyncio.Task | None` field; a new probe task is only created when the current task is None or done, satisfying FR-006's "at most one probe per backoff tick."

---

## §6 — V16 deliverable: four env vars

Four env vars with defaults-mean-inactive semantics:

| Var | Type | Valid range | Paired constraint | Unset behavior |
|---|---|---|---|---|
| `SACP_PROVIDER_FAILURE_THRESHOLD` | positive int | `[2, 100]` | must be set iff `WINDOW_S` is set | breaker inactive |
| `SACP_PROVIDER_FAILURE_WINDOW_S` | positive int (seconds) | `[30, 3600]` | must be set iff `THRESHOLD` is set | breaker inactive |
| `SACP_PROVIDER_RECOVERY_PROBE_BACKOFF` | comma-separated ints | each in `[1, 600]`, 1-10 entries | independent; unset = no auto-recovery | breaker stays open until restart / key update |
| `SACP_PROVIDER_PROBE_TIMEOUT_S` | positive int (seconds) | `[1, 30]` | independent; unset = inherit LiteLLM timeout | use LiteLLM call timeout |

**Paired validation**: a cross-validator function `validate_provider_failure_paired_vars()` is added to `VALIDATORS` AFTER the two individual validators. It reads both vars and fails if exactly one is set (i.e., both set OR both unset is valid; one set without the other is invalid). This follows the spec 013 `SACP_AUTO_MODE_ENABLED` + `SACP_DMA_DWELL_TIME_S` precedent.
