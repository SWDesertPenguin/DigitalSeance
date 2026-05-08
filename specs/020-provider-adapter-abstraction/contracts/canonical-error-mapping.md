# Contract: LiteLLM exception → CanonicalError mapping

The `LiteLLMAdapter`'s `normalize_error(exc)` implementation maps every documented LiteLLM exception class to one of seven canonical categories matching spec 015 §FR-003 exactly. This document is the static authoritative table; spec 015's circuit breaker depends on stable category assignment per FR-008.

## Mapping table

| LiteLLM exception class | Canonical category | `retry_after_seconds` populated? | Rationale |
|---|---|---|---|
| `litellm.AuthenticationError` | `AUTH_ERROR` | No | API key invalid, expired, or insufficient permissions. |
| `litellm.PermissionDeniedError` | `AUTH_ERROR` | No | Same trust boundary as auth — separate category not justified. |
| `litellm.RateLimitError` | `RATE_LIMIT` | Yes (when `exc.retry_after` set) | Provider 429. Honors provider's `Retry-After` header. |
| `litellm.Timeout` | `TIMEOUT` | No | LiteLLM's wrapper for `asyncio.TimeoutError` on provider calls. |
| `litellm.APIConnectionError` | `TIMEOUT` | No | Connection-level failures; treated as transient timeouts for breaker semantics. |
| `litellm.ContextWindowExceededError` | `ERROR_4XX` | No | Request shape failure (prompt too long for model). Caller can re-prompt with shorter context — NOT a generation-quality failure. |
| `litellm.BadRequestError` | `ERROR_4XX` | No | Generic 400; malformed request payload. |
| `litellm.UnprocessableEntityError` | `ERROR_4XX` | No | 422; payload-validation failure. |
| `litellm.NotFoundError` | `ERROR_4XX` | No | 404; model name unknown to provider. |
| `litellm.ContentPolicyViolationError` | `QUALITY_FAILURE` | No | Provider refused to generate; canonical "quality failure" per spec 015. |
| `litellm.ServiceUnavailableError` | `ERROR_5XX` | No | 503; provider-side transient. |
| `litellm.InternalServerError` | `ERROR_5XX` | No | 500; provider-side. |
| `litellm.APIError` (base, status code unknown) | `UNKNOWN` | No | Fallback when no specific class matched. |
| Any other `Exception` | `UNKNOWN` | No | Last-resort fallback. Logged with full traceback in `routing_log`. |

## Implementation skeleton

```python
def _normalize_litellm_error(exc: BaseException) -> CanonicalError:
    if isinstance(exc, litellm.RateLimitError):
        return CanonicalError(
            category=CanonicalErrorCategory.RATE_LIMIT,
            retry_after_seconds=getattr(exc, "retry_after", None),
            original_exception=exc,
            provider_message=str(exc),
        )
    if isinstance(exc, (litellm.AuthenticationError, litellm.PermissionDeniedError)):
        return CanonicalError(
            category=CanonicalErrorCategory.AUTH_ERROR,
            original_exception=exc,
            provider_message=str(exc),
        )
    if isinstance(exc, (litellm.Timeout, litellm.APIConnectionError)):
        return CanonicalError(
            category=CanonicalErrorCategory.TIMEOUT,
            original_exception=exc,
            provider_message=str(exc),
        )
    if isinstance(exc, (
        litellm.ContextWindowExceededError,
        litellm.BadRequestError,
        litellm.UnprocessableEntityError,
        litellm.NotFoundError,
    )):
        return CanonicalError(
            category=CanonicalErrorCategory.ERROR_4XX,
            original_exception=exc,
            provider_message=str(exc),
        )
    if isinstance(exc, litellm.ContentPolicyViolationError):
        return CanonicalError(
            category=CanonicalErrorCategory.QUALITY_FAILURE,
            original_exception=exc,
            provider_message=str(exc),
        )
    if isinstance(exc, (litellm.ServiceUnavailableError, litellm.InternalServerError)):
        return CanonicalError(
            category=CanonicalErrorCategory.ERROR_5XX,
            original_exception=exc,
            provider_message=str(exc),
        )
    # Unknown / unmapped — log full traceback at consumer
    return CanonicalError(
        category=CanonicalErrorCategory.UNKNOWN,
        original_exception=exc,
        provider_message=str(exc),
    )
```

## Test contract

`tests/test_020_canonical_error_mapping.py` MUST cover every row of the mapping table:

- Construct or simulate each LiteLLM exception class.
- Pass it to `_normalize_litellm_error(exc)`.
- Assert the returned `CanonicalError.category` matches the expected canonical value.
- For `RateLimitError`, assert `retry_after_seconds` is populated when the exception carries `retry_after`.
- For `UNKNOWN` fallback, construct a non-LiteLLM `Exception` subclass and assert the fallback path.

The test is a contract — adding a new LiteLLM exception class without updating this table AND the mapping function fails the test by way of the `UNKNOWN` fallback firing where a specific category was expected. CI surfaces the gap immediately.

## Cross-spec consumer (spec 015)

Spec 015's circuit breaker invokes `adapter.normalize_error(exc)` at every dispatch failure point and switches on `canonical.category`:

```python
canonical = adapter.normalize_error(exc)
match canonical.category:
    case CanonicalErrorCategory.RATE_LIMIT:
        breaker.record_failure(participant_id, kind="rate_limit",
                               retry_after=canonical.retry_after_seconds)
    case CanonicalErrorCategory.AUTH_ERROR:
        breaker.record_failure(participant_id, kind="auth_error")
    case CanonicalErrorCategory.TIMEOUT:
        breaker.record_failure(participant_id, kind="timeout")
    case CanonicalErrorCategory.ERROR_5XX:
        breaker.record_failure(participant_id, kind="error_5xx")
    case CanonicalErrorCategory.ERROR_4XX:
        # 4xx is typically a request-shape failure — don't trip the breaker
        pass
    case CanonicalErrorCategory.QUALITY_FAILURE:
        breaker.record_failure(participant_id, kind="quality_failure")
    case CanonicalErrorCategory.UNKNOWN:
        breaker.record_failure(participant_id, kind="unknown")
```

The migration of spec 015's existing `except litellm.*Error` blocks to this canonical-category dispatch lands in the same single-PR cutover per FR-005's architectural-test discipline.

## Mock adapter parity

The mock adapter's `normalize_error(exc)` MUST return canonical categories with the same semantics — when a fixture injects a `canonical_category="rate_limit"` error mode (per `contracts/mock-fixtures.md`), the resulting `CanonicalError` MUST be indistinguishable from the LiteLLM adapter's mapping of a `RateLimitError`. This parity is what lets spec 015's tests run against the mock adapter without network per SC-003.

## Rationale for non-obvious choices

- **`ContextWindowExceededError → ERROR_4XX` (not `QUALITY_FAILURE`)**: the failure is a request-shape problem (prompt too long), not a generation problem. The breaker should NOT trip on an oversized prompt; the orchestrator's context assembly should re-trim and retry. Treating this as `QUALITY_FAILURE` would conflate two different failure modes and trip the breaker unnecessarily.
- **`APIConnectionError → TIMEOUT` (not `ERROR_5XX`)**: connection-level failures are transient infrastructure issues — DNS, TCP reset, certificate hiccup — and the breaker treats them like timeouts (retry-with-backoff). Treating them as `ERROR_5XX` would incorrectly attribute provider-side fault.
- **`PermissionDeniedError → AUTH_ERROR`**: same trust boundary as auth — both surface "the credential cannot perform this operation". Splitting them into separate categories complicates spec 015's policy without adding signal.
- **`UNKNOWN` fallback intentionally exists**: if a future LiteLLM exception class lands without an entry in the mapping table, the system continues to function (errors are logged + breaker increments on UNKNOWN) rather than crashing on an unhandled exception type. The test suite catches the regression by surfacing UNKNOWN where a specific category was expected.
