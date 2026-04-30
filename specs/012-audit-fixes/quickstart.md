# Quickstart: Pre-Phase-3 Audit Cross-Cutting Deliverables

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This guide explains how to interact with the new gates and deliverables shipped under feature 012-audit-fixes. It targets developers, deploy operators, and reviewers.

---

## For developers

### Adding a new SACP_* env var (V16)

1. Add the var to `src/config/validators.py` with a documented type, valid range, and fail-closed validation rule.
2. Add a section to `docs/env-vars.md` matching the contract in [contracts/env-vars-doc.md](./contracts/env-vars-doc.md).
3. Use the var in code via the existing read mechanism (`os.getenv` or pydantic Settings).
4. Run `python -m src.run_apps --validate-config-only` locally with the new var to confirm validation works.
5. CI gate `scripts/check_env_vars.py` (or extension) blocks the PR if the var is in code but not in the doc.

### Adding a new FR to any spec

1. Add the FR line to `specs/NNN-<slug>/spec.md`.
2. Bump the spec version header per the convention in [research.md Decision 3](./research.md):
   ```markdown
   **Spec Version**: 1.1.0 | **Last Amended**: 2026-XX-XX | **Amended In**: PR #NNN (FR-NN added)
   ```
3. Add a row to the corresponding section in `docs/traceability/fr-to-test.md`. Reference the test that covers it, OR mark `untested` with a Phase-N trigger note.
4. CI gate `scripts/check_traceability.py` blocks the PR if the FR has no traceability entry.

### Adding an alembic migration

1. Create `alembic/versions/NNN_<slug>.py`. Forward-only (`downgrade()` body is `pass`).
2. Update `tests/conftest.py` raw DDL to mirror the new schema.
3. Run `python scripts/check_schema_mirror.py` locally. Must exit `0`.
4. CI gate runs the same check; fails on drift.

### Adding a new architectural decision

1. Pick the next available number under `docs/adr/` (e.g., `0002-…`).
2. Use MADR 4.0 lightweight format (see `docs/adr/0001-fire-and-forget-summarization.md` reference example).
3. Status: `proposed` initially; `accepted` after review; `superseded by NNNN` if replaced later.

### Running tests

```bash
# Unit tests only (fast)
pytest tests/unit/

# Integration tests only (slower; run separately in CI per FR-015)
pytest -m integration

# Full suite (unit + integration; matches CI default)
pytest
```

The new `integration` marker is configured in `pyproject.toml`. Tests that need a real Postgres + orchestrator + LiteLLM bridge are marked `@pytest.mark.integration`.

---

## For deploy operators

### Validating config before starting the app

```bash
python -m src.run_apps --validate-config-only
```

Exit codes: `0` = all SACP_* vars valid; `1` = at least one var invalid (failing var name + reason on stderr). Run this in your deploy pipeline BEFORE starting the orchestrator.

If you skip this, the orchestrator will still validate at startup and exit non-zero on invalid config — the validate-only mode is just a faster smoke test.

### Per-stage timing visibility

After this feature lands, every `routing_log` row has the per-stage timings populated:

```sql
SELECT route_ms, assemble_ms, dispatch_ms, persist_ms, advisory_lock_wait_ms
FROM routing_log
WHERE session_id = '<uuid>'
ORDER BY created_at DESC
LIMIT 100;
```

Same for `security_events.layer_duration_ms` per pipeline layer. Use these to diagnose perf regressions per-stage rather than aggregate-only (per Constitution §12 V14).

### Facilitator override (if §4.9 lands as approach (b))

When a facilitator approves a held draft that re-flags during re-validation, the UI prompts for a justification. The justification is recorded as:

```sql
SELECT event_type, override_reason, override_actor_id, created_at
FROM security_events
WHERE event_type = 'facilitator_override'
ORDER BY created_at DESC;
```

Required columns: `override_reason` ≥ 16 chars (low-friction overrides rejected by the UI), `override_actor_id` is the facilitator who approved.

### Operational runbook

`docs/operational-runbook.md` is the single playbook for deploy / restore / rotate / incident-response procedures. It cross-references `docs/env-vars.md`, `docs/retention.md`, `docs/error-codes.md`, and `docs/red-team-runbook.md`.

---

## For reviewers

### Auditing FR coverage

Open `docs/traceability/fr-to-test.md` and find the relevant spec section. Every FR in every spec has either a test path or an `untested` tag with a Phase-N trigger note. CI guards this so the artifact stays current.

### Auditing role × permission

Open `docs/roles-permissions.md`. Every permission-gated operation is in the matrix; cells indicate access per role with footnoted caveats.

### Auditing compliance

Open `docs/compliance-mapping.md`. GDPR articles, NIST controls, and AI Act references map to specific FRs across specs.

### Auditing audit follow-through

Open `AUDIT_FOLLOWTHROUGH.local.md` (gitignored — local repo only). Every audit finding closed during the pre-Phase-3 window has a row showing finding → resolution PR → verifying test → status.

### Reviewing a §4.9 / 007 §FR-005 PR

If the PR amends 007 §FR-005 or §4.9 in `.specify/memory/constitution.md`:

1. Confirm the architectural-review session was held with a security-aware reviewer in the loop (per FR-006 acceptance scenario 1).
2. Confirm the chosen approach (a/b/c or fourth-option) is documented in the spec amendment with rationale.
3. Confirm 007 §FR-005 and §4.9 are mutually consistent (no inverse-position drift).
4. Confirm Constitution version bumped per §14.5 PATCH semantics.

---

## For Phase 3 readiness gating

Per Constitution §14.7, the pre-Phase-3 audit window is gating: Phase 3 development should not start until the audit work is sufficiently closed (per facilitator judgment — there is no fixed-percentage gate).

**Status check**: open `AUDIT_PLAN.local.md`. Cross-cutting items checkboxes show progress on the items in this feature's scope. Per-spec amendments live on their own `fix/<slug>` branches per Constitution §14.7.5.

**Closeout signal**: when the facilitator declares the window closed, this feature's spec gets a final status update (`Status: Closed (audit window concluded YYYY-MM-DD)`) and Phase 3 work begins on its own numbered branches.
