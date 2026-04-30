# Contract: `--validate-config-only` CLI flag

**Source**: spec FR-004, FR-005 | **Plan**: `src/run_apps.py` modification, new `src/config/validators.py`

## Shape

```text
$ python -m src.run_apps --validate-config-only
```

## Behavior

- Reads every `SACP_*` env var documented in `docs/env-vars.md`.
- Calls `src.config.validators.validate_all()`.
- On success: writes `config validation: OK (NN vars validated)` to stdout, exits `0`.
- On failure: writes `config validation: FAIL` to stdout, then for each invalid var, writes `  <SACP_VAR_NAME>: <reason>` to stderr (one var per line), then exits `1`. Multiple invalid vars all reported in a single run (no early exit on first failure).
- Does NOT bind any port. Does NOT initialize the FastAPI app. Does NOT connect to the database.
- Honors `--quiet` flag if added later (suppresses stdout success line).

## Error message format

```text
config validation: FAIL
  SACP_CONVERGENCE_THRESHOLD: value '2.0' out of range; must be 0.0 < x <= 1.0
  SACP_TURN_TIMEOUT_SECONDS: value '-5' out of range; must be > 0
```

## Test coverage

- Test (FR-004 acceptance 1): set invalid var, run app normally, assert `sys.exit` with non-zero code BEFORE FastAPI imports complete.
- Test (FR-004 acceptance 2): set invalid var, run with `--validate-config-only`, assert exit code `1` and stderr contains the var name.
- Test (FR-004 acceptance 2 happy path): set all valid vars, run with `--validate-config-only`, assert exit code `0` and stdout contains the success line.
- Test: multiple invalid vars all reported in the same run.

## Interaction with existing entrypoints

- `python -m src.run_apps` (no flag) — runs `validate_all()` synchronously before binding any port; same exit semantics on failure.
- `python -m src.run_apps --validate-config-only` — runs validation only; does not start the server.
- Future flags (e.g., `--migrate-only`) would chain similarly.
