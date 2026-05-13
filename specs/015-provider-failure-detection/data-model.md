# Data Model: Provider Failure Detection and Isolation

**Branch**: `015-provider-failure-detection` | **Date**: 2026-05-13 | **Plan**: [plan.md](./plan.md)

---

## In-Memory Entities (session-local, not persisted across restart)

### CircuitState

One instance per active `(session_id, participant_id, provider, api_key_fingerprint)` tuple. Stored in a process-scope dict keyed on that tuple. Created on first failure recording or first `is_open()` call for a participant; absent entry means `closed`.

```python
@dataclass
class CircuitState:
    session_id: str
    participant_id: str
    provider: str
    api_key_fingerprint: str          # first 8 hex chars of SHA-256(api_key_encrypted)
    state: Literal["closed", "open", "half_open"]
    opened_at: datetime | None        # None when closed
    failure_window: deque             # deque of FailureRecord, maxlen bounded
    probe_schedule_position: int      # index into parsed backoff tuple
    _probe_task: asyncio.Task | None  # out-of-band probe task; None when no probe in flight
    consecutive_open_turns: int       # counts consecutive skipped turns for auto-pause trigger
```

Field invariants:
- `state == "closed"` implies `opened_at is None` and `consecutive_open_turns == 0`.
- `state in ("open", "half_open")` implies `opened_at is not None`.
- `_probe_task is not None` only when `state == "half_open"` and probe is in flight.

### FailureRecord

One entry per counted failure in the sliding window.

```python
@dataclass(frozen=True, slots=True)
class FailureRecord:
    timestamp: datetime               # UTC, used for window trimming
    failure_kind: CanonicalErrorCategory  # from src/api_bridge/adapter.py
```

Stored in `CircuitState.failure_window` (a `collections.deque`). Entries older than `SACP_PROVIDER_FAILURE_WINDOW_S` seconds are trimmed on read before counting. The deque's `maxlen` is set to `max(SACP_PROVIDER_FAILURE_THRESHOLD * 4, 20)` so it self-limits even under sustained failures (research.md §2).

---

## DB Audit Tables (append-only, no UPDATE/DELETE)

Migration: `alembic/versions/023_circuit_breaker_audit.py`

### provider_circuit_open_log

Emitted when a breaker trips from `closed` to `open` (FR-012, US3 AS1).

```sql
CREATE TABLE provider_circuit_open_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL,
    participant_id  TEXT NOT NULL,
    provider        TEXT NOT NULL,
    api_key_fingerprint TEXT NOT NULL,
    trigger_reason  TEXT NOT NULL,   -- 'error_5xx' | 'error_4xx' | 'auth_error' |
                                     --   'rate_limit' | 'timeout' | 'quality_failure' | 'unknown'
    failure_count   INTEGER NOT NULL,
    window_seconds  INTEGER NOT NULL,
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_circuit_open_session ON provider_circuit_open_log (session_id, opened_at DESC);
```

`trigger_reason` is the dominant `failure_kind` in the window at the moment of trip (mode of the failure_kind values).

### provider_circuit_probe_log

Emitted on each probe attempt during recovery (FR-012, US3 AS4).

```sql
CREATE TABLE provider_circuit_probe_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL,
    participant_id  TEXT NOT NULL,
    provider        TEXT NOT NULL,
    api_key_fingerprint TEXT NOT NULL,
    probe_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    probe_outcome   TEXT NOT NULL,   -- 'success' | 'failure' | 'timeout'
    probe_latency_ms INTEGER NOT NULL,
    schedule_position INTEGER NOT NULL,
    schedule_exhausted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_circuit_probe_session ON provider_circuit_probe_log (session_id, probe_at DESC);
```

`schedule_exhausted` is TRUE on the first probe of each cycle-restart (FR-009 single-entry-per-exhaustion semantics).

### provider_circuit_close_log

Emitted when a breaker closes — either via successful probe (auto-recovery) or `update_api_key` fast-close (FR-016). Fields per US3 AS3.

```sql
CREATE TABLE provider_circuit_close_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL,
    participant_id  TEXT NOT NULL,
    provider        TEXT NOT NULL,
    api_key_fingerprint TEXT NOT NULL,
    closed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_open_seconds INTEGER NOT NULL,
    probes_attempted INTEGER NOT NULL,
    probes_succeeded INTEGER NOT NULL,
    trigger_reason  TEXT NOT NULL    -- 'probe_success' | 'api_key_update'
);
CREATE INDEX idx_circuit_close_session ON provider_circuit_close_log (session_id, closed_at DESC);
```

---

## conftest.py schema mirror

Per `feedback_test_schema_mirror`: the three table DDLs above MUST be added to the raw schema in `tests/conftest.py` in the same task as the alembic migration. CI builds the schema from `conftest.py`, not from migrations; a mismatch only surfaces in CI.

---

## Migration chain

```
... -> 019 -> 021 -> 023
```

Current head on main is 021 (`participant_standby_modes`). Revision 022 is pre-allocated by spec 030 Phase 4 (`022_oauth_state_tables.py`). This spec uses 023 (`023_circuit_breaker_audit.py`, `down_revision = "021"`). If spec 030 merges before this spec, update `down_revision` to `"022"` for a clean linear chain. If this spec merges first, a merge migration will be needed when spec 030 lands. Note: revision 020 is intentionally absent from the chain.

---

## Persistence decision

Circuit state is **session-local and not persisted across restart**. On orchestrator restart, every breaker starts `closed`; the failure window is empty; probe schedule position resets to 0. This matches spec §Assumptions ("session-local circuit-state model is assumed sufficient for v1") and avoids the complexity of merging stale persisted state with a fresh session after a crash. The audit tables (`provider_circuit_open_log` etc.) provide the forensic record; per-session in-memory state is sufficient for v1 operation.
