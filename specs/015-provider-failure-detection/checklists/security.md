# Security Checklist: Provider Failure Detection and Isolation (spec 015)

**Branch**: `015-provider-failure-detection` | **Date**: 2026-05-13

Status words: [PASS] [PARTIAL] [GAP] [DRIFT] [ACCEPTED]

---

## Sovereignty Isolation (FR-010, V1)

- [PASS] Circuit state dict is keyed on full `(session_id, participant_id, provider, api_key_fingerprint)` tuple; no entry is read by any method that targets a different key.
- [PASS] `is_open()` and `record_failure()` take the full key tuple; no method takes only `provider` or only `session_id`.
- [PASS] Two participants sharing the same upstream provider endpoint have independent dict entries and independent state machines — confirmed by SC-007 contract test.
- [PASS] Rate-limit errors (HTTP 429) with `Retry-After` headers set `opened_at` cooldown to `max(configured_cooldown, Retry-After)` per spec edge case; the `Retry-After` value flows from `CanonicalError.retry_after_seconds` and is applied per-participant, not globally.
- [PASS] `api_key_fingerprint` in the circuit key is the first 8 hex chars of SHA-256 of the encrypted key — not the key itself; no key material stored in process-scope dict.

## No Transparent Fallback (FR-011, V1 §3)

- [PASS] `is_open()` returning `True` results in a skipped turn with `skip_reason = 'circuit_open'` — no re-dispatch to a different provider or model.
- [PASS] LiteLLM ordered-fallback list is validated at startup (FR-011 startup check) to be empty or contain only same-identity entries; cross-identity fallback config causes `SystemExit` at startup.
- [PASS] The startup check is enforced before any port binding — no window where a malformed config could slip through on a late-arriving request.
- [PASS] SC-008 contract test verifies the startup check fires on a cross-identity fallback list injection.

## Probe Call Isolation (FR-007)

- [PASS] Probe uses `adapter.validate_credentials(api_key, model)` — no message list, no token spend.
- [PASS] Probe result is written only to `provider_circuit_probe_log`; no write to `messages`, `routing_log`, or any transcript table.
- [PASS] No WS event is emitted for probe execution or result.
- [PASS] Probe is launched as `asyncio.create_task` and MUST NOT block the turn loop for any other participant (V14).

## Audit Completeness (FR-012)

- [PASS] Every `closed -> open` transition writes a `provider_circuit_open_log` row before the skip is returned to the caller.
- [PASS] Every probe attempt (success, failure, timeout) writes a `provider_circuit_probe_log` row.
- [PASS] Every `* -> closed` transition writes a `provider_circuit_close_log` row with `trigger_reason` discriminating `probe_success` from `api_key_update`.
- [PASS] Schedule-exhaustion events are recorded: `schedule_exhausted=TRUE` on the first probe log row of each cycle-restart at the last backoff interval (FR-009).
- [PASS] All three audit tables are append-only; no UPDATE or DELETE path exists in the implementation.

## Failure Type Classification (FR-003)

- [PASS] Failure classification uses `CanonicalErrorCategory` from `src/api_bridge/adapter.py` — the seven-value taxonomy defined jointly for spec 015 + 020.
- [PASS] `AUTH_ERROR` (HTTP 401/403) counts toward the threshold; an auth failure does not silently pass as a success and allow dispatch to continue burning tokens on a revoked key.
- [PASS] `RATE_LIMIT` (HTTP 429) counts as a failure with `retry_after_seconds` influencing the cooldown; the operator-stated retry guidance is respected per spec edge case.
- [PASS] `QUALITY_FAILURE` (§6.6 detection: empty response, repetition, framing break) counts toward the threshold — quality and infrastructure failures share the counter; the breaker does not distinguish within the threshold check.
- [PASS] `UNKNOWN` category counts as a failure; no exception type silently bypasses the circuit breaker.

## Additional Security Properties

- [PASS] Consecutive open-state turns counter (`consecutive_open_turns`) triggers the existing auto-pause path at 3+ turns (FR-005) — prevents indefinite silent skipping without operator notification.
- [PASS] Fast-close via `update_api_key` cancels any in-flight probe task to avoid a race where a stale probe outcome re-opens a just-closed circuit.
- [PASS] The circuit key changes on key rotation (new `api_key_fingerprint`); the old entry is evicted — a rotated-but-still-tripped breaker does not silently carry over to the new key identity.
- [PASS] `SACP_PROVIDER_FAILURE_THRESHOLD` valid range lower bound is 2 (not 1) — prevents tripping on any single isolated failure, which would be a denial-of-service vector for flaky providers.
- [PASS] Env-var paired validation ensures the threshold and window are both set or both unset; a threshold with no window (or vice versa) is rejected at startup, preventing an accidentally-always-open breaker.
