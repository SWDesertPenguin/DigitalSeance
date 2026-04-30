# Contract: schema-mirror CI gate

**Source**: spec FR-008 | **Plan**: new `scripts/check_schema_mirror.py`, CI workflow update

## Shape

```text
$ python scripts/check_schema_mirror.py
```

## Behavior

- Imports the alembic migration chain (`alembic/versions/*.py`), applies all migrations against an in-memory SQLite or temporary Postgres, dumps the resulting schema.
- Imports `tests/conftest.py`'s raw DDL block (the `_RAW_DDL` constant or equivalent), applies it against a separate temporary DB, dumps the resulting schema.
- Diffs the two schema dumps (column names, types, nullabilities, primary keys, foreign keys, indexes).
- On match: writes `schema mirror: OK (NN tables verified)` to stdout, exits `0`.
- On drift: writes `schema mirror: FAIL` to stdout, then a unified diff to stderr, then exits `1`.

## Drift reporting

The diff identifies, per-table:

- Columns present in alembic but missing from conftest (most common drift class — recurring per memory `feedback_test_schema_mirror.md`).
- Columns present in conftest but missing from alembic (rare; usually a stale conftest after an alembic drop).
- Columns where types/nullabilities/defaults differ.
- Indexes / FKs added on one side but not the other.

## Drift resolution guidance

The error message MUST include a one-line pointer:

```text
To resolve: edit tests/conftest.py raw DDL to match the alembic-derived schema. See
memory feedback_test_schema_mirror.md for context.
```

## CI integration

Runs as a CI step in the `pre-test` phase (before pytest). Fails the build on non-zero exit. Should NOT depend on Postgres being running (use SQLite or in-process Postgres so the gate is fast and runnable on every PR).

## Test coverage (meta-test)

- Test: synthetic alembic migration adding a column not reflected in conftest → script exits `1` with diff output.
- Test: matching alembic + conftest → script exits `0`.
- Test: column type drift (alembic says VARCHAR, conftest says TEXT) → script exits `1` with type-difference message.
