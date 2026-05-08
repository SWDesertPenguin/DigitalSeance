# Quickstart: Pluggable Provider Adapter Abstraction

Operator-facing workflows for verifying the adapter abstraction is in effect, switching between adapters, and diagnosing dispatch behavior. The default deployment configuration preserves pre-feature LiteLLM dispatch byte-identically per FR-014; this quickstart covers the operator paths beyond the default.

## 1. Verify the default LiteLLM adapter is active

After deploying spec 020, the orchestrator's startup log emits a banner line confirming which adapter is active:

```
[startup] Provider adapter: litellm (default; SACP_PROVIDER_ADAPTER unset or =litellm)
```

If the banner is missing or names a different adapter, your `.env` likely overrides the default — check `SACP_PROVIDER_ADAPTER`.

To verify byte-identical regression behavior:

```bash
# From the repo root
docker compose up -d
docker compose exec orchestrator pytest tests/ -k "not test_020_"
```

Every pre-feature test MUST pass without changes (SC-001 regression contract). If any test fails, compare the failing test against the LiteLLM adapter's translation logic — the regression is a defect, not a behavior change.

## 2. Verify the architectural test (FR-005)

The architectural test `tests/test_020_no_litellm_imports.py` scans `src/` for `import litellm` / `from litellm` outside the `src/api_bridge/litellm/` package:

```bash
docker compose exec orchestrator pytest tests/test_020_no_litellm_imports.py -v
```

Output:

```
test_020_no_litellm_imports.py::test_no_litellm_imports_outside_adapter PASSED
```

If the test fails, the failure message names the offending file and line. Migrate it to use `from src.api_bridge.adapter import get_adapter` per [contracts/adapter-interface.md](./contracts/adapter-interface.md).

## 3. Switch to the mock adapter for testing

The mock adapter enables deterministic dispatch without network access — useful for staging environments, offline development, and spec 015 circuit-breaker testing.

### Step 1: prepare a fixture file

Copy a sample fixture from `tests/fixtures/mock_adapter/` or write your own per [contracts/mock-fixtures.md](./contracts/mock-fixtures.md):

```bash
cp tests/fixtures/mock_adapter/basic_responses.json /etc/sacp/mock_fixtures.json
```

### Step 2: set env vars

In your `.env`:

```
SACP_PROVIDER_ADAPTER=mock
SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH=/etc/sacp/mock_fixtures.json
```

### Step 3: restart the orchestrator

```bash
docker compose restart orchestrator
```

Startup banner confirms the switch:

```
[startup] Provider adapter: mock (fixtures: /etc/sacp/mock_fixtures.json)
[startup] Loaded 5 response fixtures, 7 error fixtures, 2 capability sets.
```

If startup fails with `SACP_PROVIDER_ADAPTER=mock requires SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH to be set`, the cross-validator caught the dependency — set the path var. If startup fails with `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH=<path> contains invalid JSON`, fix the fixture file's syntax.

### Step 4: confirm no network egress

In a separate shell:

```bash
docker compose exec orchestrator python -c "
from src.api_bridge.adapter import get_adapter
adapter = get_adapter()
print(type(adapter).__name__)
"
```

Output:

```
MockAdapter
```

Run a session through the mock; verify with `tcpdump` or your network monitor that the orchestrator container makes no outbound HTTP requests.

### Step 5: rollback to LiteLLM

Unset both env vars (or set `SACP_PROVIDER_ADAPTER=litellm`), restart. Startup banner reverts to LiteLLM.

## 4. Add a future provider-specific adapter

A future spec (e.g., a direct-Anthropic adapter) extends the abstraction. The mechanical steps for landing it:

### Step 1: create the adapter package

```
src/api_bridge/anthropic_direct/
├── __init__.py        # AdapterRegistry.register("anthropic_direct", AnthropicDirectAdapter)
├── adapter.py         # AnthropicDirectAdapter class
├── dispatch.py        # direct Anthropic SDK calls
├── errors.py          # Anthropic SDK exception → CanonicalError mapping
├── streaming.py       # Anthropic stream → SACP StreamEvent normalization
├── capabilities.py    # capabilities(model) lookup
└── tokens.py          # count_tokens() implementation
```

### Step 2: amend the validator

`src/config/validators.py`:

```python
def validate_provider_adapter() -> None:
    name = os.environ.get("SACP_PROVIDER_ADAPTER", "litellm").lower()
    valid = {"litellm", "mock", "anthropic_direct"}  # ← extended
    if name not in valid:
        raise ConfigError(...)
```

### Step 3: import the package at startup

In the orchestrator's startup hook:

```python
import src.api_bridge.litellm  # noqa: F401
import src.api_bridge.mock     # noqa: F401
import src.api_bridge.anthropic_direct  # noqa: F401  ← add this
```

### Step 4: ship

The architectural test (`test_020_no_litellm_imports.py`) continues to pass — the new adapter doesn't import `litellm`. Operators select via `SACP_PROVIDER_ADAPTER=anthropic_direct`; the registry hands out the new class.

The new adapter spec governs ITS behavior; the v1 abstraction is unchanged. This is the entire payoff of the spec — adapter swap is "implement a new class, register it, flip an env var."

## 5. Diagnose dispatch behavior

### Check which adapter handled a turn

`routing_log` rows include `adapter_name` (added in this spec):

```sql
SELECT turn_id, participant_id, adapter_name, dispatch_duration_ms, normalize_error_category
FROM routing_log
ORDER BY created_at DESC
LIMIT 10;
```

### Verify canonical-error mapping

When a dispatch fails, `routing_log` stores both the original exception class name AND the canonical category:

```sql
SELECT turn_id,
       adapter_name,
       original_exception_class,
       normalize_error_category,
       retry_after_seconds
FROM routing_log
WHERE normalize_error_category IS NOT NULL
ORDER BY created_at DESC
LIMIT 20;
```

Cross-check against [canonical-error-mapping.md](./contracts/canonical-error-mapping.md) — every original exception class MUST map to a category per the contract table. If a row shows `normalize_error_category='unknown'` for a class that should map to a specific category, the mapping table missed it; file a fix-PR amending `src/api_bridge/litellm/errors.py` and the mapping contract.

### Verify the `provider_family` label

Spec 016 metrics tag every dispatch with `provider_family`. To verify the bounded-enum mapping is correct:

```sql
SELECT DISTINCT provider_family, count(*)
FROM routing_log
GROUP BY provider_family;
```

Expected values: `anthropic`, `openai`, `gemini`, `groq`, `ollama`, `vllm`, `unknown`, `mock`. Any other value indicates a bug in [research.md §12](./research.md)'s mapping table.

## 6. Recovery from misconfiguration

| Symptom | Likely cause | Fix |
|---|---|---|
| Startup exits with `SACP_PROVIDER_ADAPTER=<name> not in registered adapter names` | Env var typo or unregistered adapter name | Check spelling; verify the adapter package is imported at startup |
| Startup exits with `SACP_PROVIDER_ADAPTER=mock requires SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH to be set` | Cross-validator caught missing path | Set the path var or change the adapter |
| Startup exits with `SACP_PROVIDER_ADAPTER_MOCK_FIXTURES_PATH=<path> is not a readable file` | Path wrong, file permissions wrong | Check the path; check container volume mounts |
| Startup exits with `... contains invalid JSON` | Fixture file syntax error | Validate with `python -m json.tool < fixture.json` |
| `RuntimeError: Adapter not initialized. Call initialize_adapter() during startup.` | Code path runs before lifespan startup hook | Initialization regression — file a bug |
| `RuntimeError: Adapter already initialized; mid-process swap is OUT OF SCOPE per spec 020 FR-015.` | Code attempted re-init | Code regression — file a bug |
| All dispatches fail with `MockFixtureMissing: <hash>` | Mock adapter selected but no matching fixture | Add the missing fixture; the exception names the canonical hash and a substring of the last message for easy lookup |
| Topology 7 deployment errors with `topology 7 has no bridge layer` | A code path is calling `get_adapter()` in topology 7 | Code regression — that code path needs topology gating |

## 7. Performance characterization

### V14 budget 1: adapter-call overhead per dispatch

The abstraction MUST add no measurable overhead over direct LiteLLM calls. To verify:

```sql
SELECT
  adapter_name,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY dispatch_duration_ms) AS p50,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY dispatch_duration_ms) AS p95,
  percentile_cont(0.99) WITHIN GROUP (ORDER BY dispatch_duration_ms) AS p99
FROM routing_log
WHERE created_at > now() - interval '1 hour'
GROUP BY adapter_name;
```

Compare LiteLLM-adapter latency to pre-feature LiteLLM dispatch latency (captured in your historical metrics). The delta MUST fit within V14 per-stage budget tolerance per spec §"Performance Budgets".

### V14 budget 2: `normalize_error()` execution

Spec 015's audit entries record the `normalize_error` duration:

```sql
SELECT
  percentile_cont(0.50) WITHIN GROUP (ORDER BY normalize_error_duration_us) AS p50_us,
  percentile_cont(0.99) WITHIN GROUP (ORDER BY normalize_error_duration_us) AS p99_us
FROM security_events
WHERE event_type = 'circuit_breaker_increment'
  AND created_at > now() - interval '24 hours';
```

Both percentiles MUST be in single-digit microseconds (constant-time `O(1)` per V14 budget 2). Anything slower indicates the mapping function grew an I/O path; investigate.

## 8. Cross-spec verification

After deploying spec 020, verify the consumers integrate cleanly:

- **Spec 015 circuit breaker**: trigger each `CanonicalErrorCategory` value via the mock adapter's error fixtures; assert breaker increments per spec 015's per-category cooldown logic.
- **Spec 016 metrics**: query Prometheus for `sacp_provider_dispatch_total{provider_family=~"anthropic|openai|gemini|groq|ollama|vllm|mock"}`; assert the bounded enum is respected.
- **Spec 017 freshness**: trigger a tool-list change with a model whose `capabilities().supports_prompt_caching=true`; assert the prompt-cache invalidation logic fires.
- **Spec 018 deferred-loading**: load a participant whose `capabilities().max_context_tokens=8192` (e.g., the mock adapter's `no_tool_model` fixture); assert deferred-loading partitions kick in.

These cross-spec checks are NOT mandated by spec 020's tasks but are recommended verification steps before declaring the rollout stable.
