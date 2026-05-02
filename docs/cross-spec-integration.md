# Cross-Spec Integration Tests

This document codifies the integration-test tier that exercises spec
BOUNDARIES rather than any single spec in isolation. Cross-referenced
from `AUDIT_PLAN.local.md` Batch 4 → "Cross-spec integration testing"
cross-cutting audit. Phase F deliverable from
`fix/cross-spec-integration`.

---

## Tier shape

Two CI tiers ship today (per `.github/workflows/test.yml` and
`pyproject.toml::markers`):

- **Unit tier** (`pytest -m "not integration"`): per-module tests, mocked
  dependencies, runs against the test Postgres fixture but only the bits
  the test needs. Fast (< 30s for the full suite).
- **Integration tier** (`pytest -m integration`): cross-spec boundary
  tests, real orchestrator + DB + mocked LiteLLM. Slower per test
  (~100ms-1s each); runs in its own CI step so a slow integration test
  doesn't drag the unit tier latency.

Tests live in:

- `tests/test_<topic>.py` — per-module / per-spec unit tests.
- `tests/integration/test_<boundary>.py` — cross-spec integration tests.
  Every file in this directory MUST mark its tests with
  `@pytest.mark.integration` (verified by `tests/integration/conftest.py`).

The `tests/test_loop_integration.py` and `tests/test_mcp_e2e.py` files
predate this layout convention; they're integration-shaped (real DB +
mocked LiteLLM) but live in the unit tier today. Migrating them under
the marker is a Phase 3 follow-up — out of scope for the boundary
catalogue this document establishes.

---

## Boundary catalogue

These are the cross-spec seams that the integration tier covers (or
will cover; deferred items are flagged):

| ID | Boundary | Coverage today |
|---|---|---|
| INT-001 | 003 turn-loop → 007 pipeline → 008 wiring | `tests/integration/test_pipeline_through_loop.py` (turn fires; sanitize + exfil run; cleaned message persisted) |
| INT-002 | 003 turn-loop → 004 convergence | DEFERRED — convergence model load is heavy; activate with a shared-fixture-cached embedding |
| INT-003 | 003 turn-loop → 005 summarizer trigger | `tests/integration/test_summarizer_trigger.py` (threshold crossing fires `run_checkpoint`; FK fail-closed verified) |
| INT-004 | 005 summarizer → 002 facilitator-id attribution | covered by INT-003 (speaker_id of stored summary == facilitator_id) |
| INT-005 | 010 debug-export → 001 + 004 + 007 reads | covered structurally by `tests/test_mcp_e2e.py::test_debug_export_as_facilitator` (does not yet carry the integration marker — see migration note) |
| INT-006 | 011 web-ui → 002 auth + 006 MCP API | DEFERRED — Playwright fixture lands with web-vitals follow-up |

---

## Fixture sharing

Integration tests SHARE the same Postgres fixture chain as unit tests:

- `pool` (function-scoped) — fresh, truncated tables per test.
- `session_with_participant` — pre-built session + facilitator + AI
  participant.
- `mock_litellm` — patched `litellm.acompletion` returning a
  deterministic synthetic response.
- `mcp_app` / `web_app` — per-test FastAPI app instances (spec 012
  FR-009 / US7); use these instead of importing the global app to
  avoid middleware-state leak across tests.

If a new integration test needs a more complex setup (e.g., multi-
participant session with seeded messages and convergence state), add
the fixture to `tests/conftest.py` (NOT `tests/integration/conftest.py`)
so unit-tier tests can share it. Integration-only fixtures live in
`tests/integration/conftest.py`.

---

## Runtime budget

Integration tests SHOULD aim for:

- Per-test budget ≤ 1 second wall-clock on a representative dev host.
- Total integration-tier budget ≤ 30 seconds for the full suite.
- Anything exceeding 5 seconds for a single test is a code smell:
  either the test is doing too much (split it), or the production
  path is slow (file an audit-plan ops item).

The `tests/integration/test_pipeline_through_loop.py` test today runs
in ~150ms; INT-003 in ~250ms. Plenty of headroom for the catalogue
to grow.

---

## Marker enforcement

`tests/integration/conftest.py` adds `pytest.mark.integration` to every
test in the directory automatically. New files don't need to remember
the marker per-test; just landing under `tests/integration/` is enough.

The CI runner (`.github/workflows/test.yml`) executes
`pytest -m integration` as a separate step. The job tolerates exit code 5
("no tests collected") with a notice — useful during the pre-Phase-3
audit window when the boundary catalogue is small. Once INT-001 lands,
the integration tier will execute real tests on every PR.

---

## Phase 3 follow-up

- Migrate `tests/test_loop_integration.py` + `tests/test_mcp_e2e.py`
  under the integration marker. These are integration-shaped today
  but live in the unit tier; runtime + scope make them natural
  integration-tier residents.
- Activate INT-002 once a shared embedding-fixture caches the
  `all-MiniLM-L6-v2` model load across tests.
- Activate INT-006 once the Playwright fixture lands (Phase 3 web-
  vitals follow-up).
- DB-backed migration tests (idempotency, replay, restore-from-old-
  backup, lock contention) currently sit as `@pytest.mark.skip`
  markers in `tests/test_migration_safety.py`; activate them under
  `@pytest.mark.integration` once a migration-runner fixture lands.
