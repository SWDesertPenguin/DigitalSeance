# Contract: provider-adapter-abstraction SACP_* env vars

Two new vars introduced in this feature. Each lands in `src/config/validators.py` AND `docs/env-vars.md` BEFORE `/speckit.tasks` per spec FR-013 (V16 deliverable gate).

## `SACP_PROVIDER_ADAPTER`

- **Default**: `"litellm"` — preserves pre-feature LiteLLM dispatch behavior (FR-014 byte-identical regression contract).
- **Type**: string, adapter name from `AdapterRegistry`. Case-folded to lowercase before lookup.
- **Valid range**: any name registered in `AdapterRegistry`. v1 ships `litellm` and `mock`; future provider-specific adapters add their names. The validator hardcodes `{"litellm", "mock"}` for v1; future adapters extend this set in their landing PRs per [research.md §9](../research.md).
- **Blast radius on invalid**: V16 startup validator refuses to bind ports. Error message lists all registered adapter names so operators see exactly what's available.
- **Validation rule**: `validators.validate_provider_adapter`
- **Source spec(s)**: 020 §FR-002 / FR-003 / SC-005

## `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH`

- **Default**: unset. Required only when `SACP_PROVIDER_ADAPTER=mock`; ignored otherwise.
- **Type**: filesystem path to a JSON fixture file (per [research.md §7](../research.md)).
- **Valid range**: must be a readable file path with valid JSON content matching the schema in [contracts/mock-fixtures.md](./mock-fixtures.md).
- **Blast radius on invalid**: V16 startup validator refuses to bind ports. Three failure modes:
  - `SACP_PROVIDER_ADAPTER=mock` and var unset — error: "SACP_PROVIDER_ADAPTER=mock requires SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH to be set".
  - Path exists but is not a readable file — error: "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH=<path> is not a readable file".
  - File contains invalid JSON — error: "SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH=<path> contains invalid JSON: <detail>".
- **Validation rule**: `validators.validate_provider_adapter_mock_fixtures_path`
- **Source spec(s)**: 020 §FR-006 / FR-007 / SC-004

## Cross-validator dependency

Per [research.md §9](../research.md), `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH` is conditionally required: when `SACP_PROVIDER_ADAPTER=mock`, the path var MUST be set + readable + parseable; when adapter is `litellm` (or any non-mock value), the path var is ignored entirely. The validator reads `SACP_PROVIDER_ADAPTER` first and applies its rules conditionally — same shape as spec 014's `SACP_AUTO_MODE_ENABLED` ↔ `SACP_DMA_DWELL_TIME_S` precedent.

Schema validation (top-level keys, fixture-entry shape, `match_mode` enum, `canonical_category` enum) happens at adapter instantiation time, not validator time, since deeper schema checks require the adapter package to be loaded. The validator only checks file existence, readability, and parse-ability; deeper validation surfaces a `MockFixtureSchemaError` at adapter init per FR-006's fail-closed semantics.

## CI-gate alignment

Per spec 012 FR-005 the `scripts/check_env_vars.py` gate scans `src/` for `os.environ.get("SACP_*")` calls and asserts each has a section in `docs/env-vars.md`. Both vars above MUST satisfy that gate before `/speckit.tasks` is run for this spec.

The validators MUST be appended to the `VALIDATORS` tuple in `src/config/validators.py` so they fire during `validate_all()` at orchestrator startup (V16 contract).

The two-validator order is documented but not enforced — `validate_provider_adapter` runs first by tuple position to surface adapter-name failures before fixture-path failures, but neither validator depends on the other's prior execution (each reads `SACP_PROVIDER_ADAPTER` independently).
