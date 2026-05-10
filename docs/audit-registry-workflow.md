# Adding a new audit action

Workflow for any spec that needs to record a new entry in `admin_audit_log` with a human-readable label in the audit-log viewer (spec 029).

The action-label registry is a paired backend/frontend artifact; both halves MUST update in the same PR or CI fails on parity. Only `src/orchestrator/audit_labels.py` and `frontend/audit_labels.js` may declare audit-action mappings — `tests/test_029_architectural.py` enforces this (FR-020).

## Steps

1. **Backend entry.** Add a row to `LABELS` in `src/orchestrator/audit_labels.py`:

   ```python
   LABELS: dict[str, dict[str, Any]] = {
       ...,
       "your_new_action": {"label": "English description of the action"},
   }
   ```

   The label is the operator-facing string the audit panel renders. Phrase it as a past-tense statement of what happened ("Facilitator removed participant", "Auth token rotated").

2. **Frontend mirror.** Add the same key + label to `LABELS` in `frontend/audit_labels.js`. The `scrub_value` flag (step 3) is intentionally backend-only — the frontend never sees the raw value, so the flag is not needed client-side.

3. **Sensitive-value scrub (optional).** If `previous_value` / `new_value` columns will carry secret material (auth tokens, encryption keys, anything that must not leave the orchestrator), add `scrub_value=True` to the backend entry:

   ```python
   "your_new_action": {"label": "...", "scrub_value": True},
   ```

   The FR-001 endpoint and FR-010 broadcast helper replace both value columns with the literal string `"[scrubbed]"` before transmission. Spec 010 debug-export still returns raw values — operators retain forensic walkability via the export path.

   When you set `scrub_value=True`, justify the choice in the amending spec's `## Clarifications` section. The existing `rotate_token` and `revoke_token` entries are precedents.

4. **Call-site wiring.** When you call `repo.log_admin_action(action="your_new_action", ...)`, pass `broadcast_session_id=<session_id>` so the new audit row pushes over WebSocket to the live viewer (FR-010). Without it, the row only shows after a panel re-fetch.

5. **CI parity gate.** `scripts/check_audit_label_parity.py` runs as a required CI step. It fails with a clear error naming the missing/divergent key when:
   - Backend `LABELS` has a key not present in frontend `LABELS`
   - Frontend `LABELS` has a key not present in backend `LABELS`
   - A key's `label` string differs between backend and frontend

6. **Tests.** Add coverage in `tests/test_029_action_label_registry.py` if the new entry has unusual semantics (scrub flag, dynamic label). The default registry-shape tests already iterate `LABELS` and verify every entry has a `label: str`.

## Where the contract lives

The full public surface — including the diff renderer and time formatter modules — is pinned in [`specs/029-audit-log-viewer/contracts/shared-module-contracts.md`](../specs/029-audit-log-viewer/contracts/shared-module-contracts.md). Specs 022 and 024 cite that document; future audit-adjacent specs should too.

## Related tests

- `tests/test_029_architectural.py` — FR-020 enforcement (no parallel mappings)
- `tests/test_029_contract_freshness.py` — citation freshness vs disk
- `tests/test_029_action_label_registry.py` — registry shape + helpers
- `scripts/check_audit_label_parity.py` — backend↔frontend key/label parity
