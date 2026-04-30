# Contract: `docs/env-vars.md`

**Source**: spec FR-005, FR-010 (env-vars.md) | **Pairs with**: FR-004 V16 implementation

## Required sections

```markdown
# SACP Environment Variable Catalog

## Conventions

- Every var is prefixed `SACP_`.
- Every var is validated at startup per Constitution §12 V16; invalid values cause the process to exit before binding any port.
- Defaults are listed as the value used when the var is unset; `<required>` indicates no default (process exits on missing).

## Per-var entries

### `SACP_<NAME>`

- **Default**: `<value>` or `<required>`
- **Type**: int / float / bool / string / URL / Fernet-key / comma-separated-list
- **Valid range**: <numeric range> / <enum values> / <regex pattern> / <free-form>
- **Blast radius on invalid**: <what fails when this is wrong>
- **Validation rule**: <pseudocode or description matching `src/config/validators.py`>
- **Source spec(s)**: <FR references>

[Repeat for every SACP_* var]

## Cross-cutting notes

- `SACP_TRUST_PROXY` interaction with `SACP_WEB_UI_INSECURE_COOKIES` (security-critical pairing)
- `SACP_AUDIT_RETENTION_DAYS` interaction with the AUDIT_PLAN purge job (FR-007 cross-ref)
- Vars deferred to Phase 3 (listed but inactive in Phase 1+2)
```

## Initial inventory (per AUDIT_PLAN batch 5 + cross-spec scan)

The doc MUST cover at minimum:

- `SACP_DB_URL` (required)
- `SACP_ENCRYPTION_KEY` (required, Fernet 44-char base64)
- `SACP_AUDIT_RETENTION_DAYS` (default 365, range ≥1 or unset-for-indefinite)
- `SACP_SECURITY_EVENTS_RETENTION_DAYS` (default 90, range ≥1 or unset)
- `SACP_TURN_TIMEOUT_SECONDS` (default 180, range >0)
- `SACP_CONTEXT_MAX_TURNS` (default 50, range ≥3)
- `SACP_CONVERGENCE_THRESHOLD` (default 0.75, range 0.0 < x ≤ 1.0)
- `SACP_TRUST_PROXY` (default 0, enum {0, 1})
- `SACP_ENABLE_DOCS` (default 0, enum {0, 1})
- `SACP_CORS_ORIGINS` (default empty, comma-separated URLs)
- `SACP_MAX_SUBSCRIBERS_PER_SESSION` (default 64, range ≥1)
- `compound_retry_total_max_seconds` (003 §FR-031, default 600, range >180)
- `SACP_WEB_UI_MCP_ORIGIN` (required for web-ui)
- `SACP_WEB_UI_WS_ORIGIN` (required for web-ui)
- `SACP_WEB_UI_ALLOWED_ORIGINS` (default empty, comma-separated URLs)
- `SACP_WEB_UI_INSECURE_COOKIES` (default 0, enum {0, 1}; warns at startup when 1)
- `SACP_LITELLM_BASE_URL` (existing pattern)
- … (full inventory closes the gap; this list is the floor, not the ceiling)

## Constitutional reference

This doc is added to Constitution §13 authoritative-references on land:

```markdown
| `docs/env-vars.md` | Configuration catalog | Per-var defaults, types, ranges, blast radius, validation rules per V16 |
```

## CI gate

`scripts/check_env_vars.py` (or extended `check_traceability.py`):

- Greps `src/` for every `os.getenv("SACP_…")` and `os.environ["SACP_…"]` call.
- Asserts every grepped var appears in `docs/env-vars.md`.
- Asserts every var listed in `docs/env-vars.md` appears in `src/config/validators.py`.
- Drift fails CI.
