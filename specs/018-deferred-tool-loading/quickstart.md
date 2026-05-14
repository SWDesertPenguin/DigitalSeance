# Quickstart: Deferred Tool Loading

**Branch**: `018-deferred-tool-loading` | **Date**: 2026-05-13

---

## Operator activation (Phase 2 only — Phase 1 is design hooks)

Deferred loading is **disabled by default**. To activate in a live deployment:

```bash
# Required: enable the partition mechanism.
export SACP_TOOL_DEFER_ENABLED=true

# Optional: customize the budget.
export SACP_TOOL_LOADED_TOKEN_BUDGET=1500    # default
export SACP_TOOL_DEFER_INDEX_MAX_TOKENS=256  # default
export SACP_TOOL_DEFER_LOAD_TIMEOUT_S=30     # default (inherits MCP client timeout)
```

Restart the orchestrator. On the next session a participant joins:
- The orchestrator resolves the participant's tokenizer via `get_tokenizer_for_participant`.
- The partition runs in registration order: first N tools that fit `SACP_TOOL_LOADED_TOKEN_BUDGET` land in the loaded subset.
- The remainder land in the deferred subset, surfaced to the model as compact index entries.
- One `tool_partition_decided` row is emitted to `admin_audit_log`.

## Verifying the Phase-1 cut (no behavioral change)

After the Phase-1 cut lands on main:

```bash
# Deferral is off by default; partition module returns empty set.
unset SACP_TOOL_DEFER_ENABLED
python -m src.run_apps --validate-config-only && echo OK

# Run the full pre-feature acceptance suite — every test passes byte-identically.
pytest tests/ --ignore=tests/e2e

# Inspect the deferred-tool index hook is consulted but returns empty.
pytest tests/test_018_phase1_hooks.py -v
```

The Phase-1 cut MUST produce byte-identical system prompts and audit logs to the pre-feature baseline. If any pre-feature test fails after the Phase-1 cut merges, the cut has a regression and the merge MUST be reverted.

## Verifying the Phase-2 cut (working partition)

After the Phase-2 cut lands and Phase 2 is activated:

```bash
# 1. Activate deferral.
export SACP_TOOL_DEFER_ENABLED=true
export SACP_TOOL_LOADED_TOKEN_BUDGET=1500

# 2. Start a session with a participant who has 20 registered tools whose
#    combined definitions exceed 1500 tokens. (Use the existing test fixture
#    or a synthetic registration.)
pytest tests/test_018_partition.py::test_us2_as1_budget_respected -v

# 3. Watch the partition decision land in the audit log.
psql -c "SELECT timestamp, action_type, payload->>'loaded_count' AS loaded, payload->>'deferred_count' AS deferred FROM admin_audit_log WHERE action_type='tool_partition_decided' ORDER BY timestamp DESC LIMIT 5"

# 4. From a test client posing as the participant, invoke tools.load_deferred:
pytest tests/test_018_discovery.py::test_us3_as1_load_promotes_tool -v
```

## Auditing partition decisions

The `admin_audit_log` table is the canonical record of every partition decision and every discovery-driven load. Operators can reconstruct any participant's partition history with a single query:

```sql
SELECT timestamp, action_type, payload
FROM admin_audit_log
WHERE session_id = '<sess_id>'
  AND participant_id = '<participant_id>'
  AND action_type IN ('tool_partition_decided', 'tool_loaded_on_demand', 'tool_re_deferred')
ORDER BY timestamp;
```

The combined timeline shows:
1. The initial `tool_partition_decided` at session start (with the full loaded/deferred name lists).
2. Each subsequent `tool_partition_decided` triggered by a spec-017 freshness refresh.
3. Each `tool_loaded_on_demand` row when the model invoked `tools.load_deferred`.
4. Each paired `tool_re_deferred` row when an LRU eviction occurred to fit budget.

## Per-participant scoping verification

To verify a participant cannot load tools from another participant's set:

```bash
# As participant A, invoke tools.load_deferred for a tool only in B's registry.
# Expected response:
#   {"error": "tool_not_in_caller_registry", "tool_name": "B_only_tool"}

pytest tests/test_018_discovery.py::test_us3_as4_cross_participant_reject -v
```

The audit log shows zero state changes on participant B from this invocation.

## Pathological partition

If a single tool's full definition exceeds `SACP_TOOL_LOADED_TOKEN_BUDGET`, the loaded subset will contain only the two discovery tools (always loaded per FR-011) and ALL other participant tools defer. The audit row sets `pathological_partition=true`:

```sql
SELECT payload
FROM admin_audit_log
WHERE action_type = 'tool_partition_decided'
  AND payload->>'pathological_partition' = 'true'
ORDER BY timestamp DESC LIMIT 5;
```

Operator remediation: raise `SACP_TOOL_LOADED_TOKEN_BUDGET`, OR re-scope the participant's tool set to use slimmer schemas.

## Tokenizer fallback verification

If the participant's model has no per-provider tokenizer adapter (rare — most paths resolve to OpenAI/Anthropic/Gemini), the partition uses the coarse `_DefaultTokenizer` and logs a WARN:

```text
WARN deferred_tool_index: tokenizer_fallback_used participant=<pid> model=<m> using=default:cl100k
```

The `tool_partition_decided` audit row reflects this with `tokenizer_fallback_used=true` and `tokenizer_name="default:cl100k"`. Partition decisions remain valid; they just use a coarse estimate.

## Rollback

To disable deferral mid-deployment without restart:

```bash
# Deferral is process-config; restart required to flip.
unset SACP_TOOL_DEFER_ENABLED
# Or:
export SACP_TOOL_DEFER_ENABLED=false
# Then restart the orchestrator.
```

In-flight sessions continue with their current partition until next session start (sessions don't re-partition mid-flight on env-var change). To force a clean state, the operator must terminate active sessions OR wait for them to conclude naturally.
