# Contract: FR-to-test traceability artifact

**Source**: spec FR-003 | **Plan**: new `docs/traceability/fr-to-test.md` + `scripts/check_traceability.py` CI gate

## Output shape

`docs/traceability/fr-to-test.md` — markdown file with one section per spec, each section containing a table:

```markdown
# FR-to-Test Traceability

## 001-core-data-model

| FR | Tests | Notes |
|---|---|---|
| FR-001 | tests/unit/test_data_model.py::test_session_create | |
| FR-002 | tests/integration/test_repos.py::test_message_persist | |
| FR-016 | tests/unit/test_participant_lifecycle.py::test_departure_scrub | |
| FR-024 | untested | Phase 3 trigger: when budget enforcement reaches multi-window correlation |

## 002-participant-auth

| FR | Tests | Notes |
|---|---|---|
| FR-001 | tests/integration/test_auth.py::test_token_format | |
...
```

## Tabular fields

| Field | Type | Description |
|---|---|---|
| FR | string | Functional requirement ID matching the source spec (`FR-001`, `FR-NNa`, etc.) |
| Tests | comma-separated list of strings | `tests/path/to/file.py::test_name`; multiple tests OK; or literal `untested` |
| Notes | string | Free-form. When `Tests = untested`, the note MUST include a Phase-N trigger explaining when the FR will be covered |

## Generation

- Initial generation is hand-curated (one PR per spec, ~10 PRs total) since automated extraction would be brittle (FR text varies in style across specs).
- Subsequent updates land in the same PR as the FR being added (CI gate enforces this — see below).

## CI gate (`scripts/check_traceability.py`)

- On every PR, parse all `specs/NNN/spec.md` for FR-NN markers.
- Parse `docs/traceability/fr-to-test.md` for tabular entries.
- Assert: every FR in every spec has an entry in the traceability artifact.
- Assert: every "tests" entry that references a test path actually resolves (the test exists and is collectible).
- Assert: every `untested` entry has a non-empty Notes field.

## Test coverage (meta-test)

- Test: a synthetic spec adds `FR-099` without a traceability entry → CI fails.
- Test: a synthetic traceability entry references `tests/nonexistent.py::test_x` → CI fails.
- Test: an `untested` entry without a trigger note → CI fails.

## Update workflow

When adding a new FR to any spec:

1. Add the FR line to the spec.
2. Add a row to the corresponding section in `docs/traceability/fr-to-test.md`.
3. If the FR has a test in this PR, reference it; if it's a Phase-3 trigger, mark `untested` with the trigger note.
4. CI gate confirms the linkage.
