# Quickstart: Facilitator Scratch Window

**Branch**: `024-facilitator-scratch` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)

## Operator enablement

The scratch feature ships behind a master switch. To enable in any deployment:

```bash
export SACP_SCRATCH_ENABLED=1
export SACP_SCRATCH_NOTE_MAX_KB=64                 # optional, default 64
export SACP_SCRATCH_RETENTION_DAYS_AFTER_ARCHIVE=  # optional, default empty (indefinite)
```

Restart the orchestrator. The startup log MUST include a structured INFO entry naming the active scope and the cap.

## Account-scoped vs session-scoped paths

| `SACP_ACCOUNTS_ENABLED` | Facilitator auth | Scope | Survives archive? |
|---|---|---|---|
| `1` | account login | `account` | Yes |
| `1` | token paste | `session` | No |
| `0` | token paste | `session` | No |

The scratch panel header chip displays the active scope so the facilitator never loses notes by surprise.

## Smoke test: write + autosave + reopen

1. Start a session.
2. Open the scratch panel from the session header.
3. Switch to the Notes tab.
4. Type a note. Wait 3 seconds (2s autosave debounce + 1s round-trip).
5. Close the panel.
6. Reopen the panel. The note appears.
7. Inspect a subsequent AI turn''s assembled prompt. The note content MUST NOT appear.

## Smoke test: promote-to-transcript

1. With a saved note open, click "Promote to transcript".
2. Confirmation modal renders showing the EXACT text.
3. Click Confirm.
4. The transcript shows the note content as a human turn.
5. The note row shows "promoted on <ts>" with a link to the transcript message.
6. Inspect `admin_audit_log` for one row with `action=''facilitator_promoted_note''`.

## Smoke test: archive-then-return (account-scoped path)

Requires `SACP_ACCOUNTS_ENABLED=1` and the facilitator logged in via account auth.

1. Take notes in a session.
2. Archive the session.
3. Log out, log back in.
4. Navigate to the archived session from `/me/sessions`.
5. Open the scratch panel. Notes are present.
6. The promote-to-transcript button is disabled with tooltip "promote requires an active session".

## Smoke test: master-switch-off

1. Set `SACP_SCRATCH_ENABLED=0` (default).
2. Restart the orchestrator.
3. Any `GET /tools/facilitator/scratch?session_id=<id>` returns HTTP 404.
4. The SPA session header does NOT show the scratch panel entry-point button.

## Smoke test: architectural test

```bash
.venv/Scripts/python.exe -m pytest tests/test_024_architectural.py -v
```

Both the import-scan and runtime-tracer layers MUST pass.

## Test invocations

```bash
# Full unit + integration suite (excludes e2e)
.venv/Scripts/python.exe -m pytest tests/ --ignore=tests/e2e

# Spec 024 tests only
.venv/Scripts/python.exe -m pytest tests/test_024_*.py -v

# Frontend Node tests
node tests/frontend/test_scratch_notes.js

# E2E (requires SACP_RUN_E2E=1 + a running orchestrator)
SACP_RUN_E2E=1 .venv/Scripts/python.exe -m pytest tests/e2e/test_024_scratch_panel.py -v
```

## Closeout preflights

Run the six preflights before declaring the spec implemented. All six MUST exit 0:

```bash
.venv/Scripts/python.exe scripts/check_env_vars.py
.venv/Scripts/python.exe scripts/check_traceability.py
.venv/Scripts/python.exe scripts/check_schema_mirror.py
.venv/Scripts/python.exe scripts/check_doc_deliverables.py
.venv/Scripts/python.exe scripts/check_audit_label_parity.py
.venv/Scripts/python.exe scripts/check_time_format_parity.py
```
