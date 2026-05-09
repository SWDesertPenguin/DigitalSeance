"""US1 acceptance scenario 4: LiteLLM exception -> CanonicalError mapping.

One assertion per row of the 14-row mapping table per
`specs/020-provider-adapter-abstraction/contracts/canonical-error-mapping.md`.
Constructs each LiteLLM exception class and confirms the canonical
category matches the contract.
"""

from __future__ import annotations

import httpx
import litellm
import pytest

from src.api_bridge.adapter import CanonicalErrorCategory
from src.api_bridge.litellm.errors import normalize_litellm_error


def _has(name: str) -> bool:
    return isinstance(getattr(litellm, name, None), type)


def _stub_response(status_code: int) -> httpx.Response:
    """Construct a minimal httpx.Response for LiteLLM error classes that require one."""
    return httpx.Response(status_code=status_code, request=httpx.Request("GET", "https://api"))


@pytest.mark.skipif(not _has("AuthenticationError"), reason="LiteLLM class missing")
def test_authentication_error_maps_to_auth() -> None:
    exc = litellm.AuthenticationError(message="bad key", llm_provider="openai", model="gpt-4o")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.AUTH_ERROR


@pytest.mark.skipif(not _has("PermissionDeniedError"), reason="LiteLLM class missing")
def test_permission_denied_maps_to_auth() -> None:
    exc = litellm.PermissionDeniedError(
        message="forbidden", llm_provider="openai", model="gpt-4o", response=_stub_response(403)
    )
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.AUTH_ERROR


def test_rate_limit_maps_to_rate_limit() -> None:
    exc = litellm.RateLimitError("rate limited", "provider", "model", None)
    canonical = normalize_litellm_error(exc)
    assert canonical.category == CanonicalErrorCategory.RATE_LIMIT


def test_rate_limit_carries_retry_after() -> None:
    exc = litellm.RateLimitError("rate limited", "provider", "model", None)
    exc.retry_after = 30  # type: ignore[attr-defined]
    canonical = normalize_litellm_error(exc)
    assert canonical.retry_after_seconds == 30


def test_timeout_maps_to_timeout() -> None:
    exc = litellm.Timeout(message="timeout", model="gpt-4o", llm_provider="openai")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.TIMEOUT


@pytest.mark.skipif(not _has("APIConnectionError"), reason="LiteLLM class missing")
def test_api_connection_error_maps_to_timeout() -> None:
    exc = litellm.APIConnectionError(message="conn dropped", llm_provider="openai", model="gpt-4o")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.TIMEOUT


def test_context_window_exceeded_maps_to_4xx() -> None:
    exc = litellm.ContextWindowExceededError(
        message="too long", model="gpt-4o", llm_provider="openai"
    )
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.ERROR_4XX


@pytest.mark.skipif(not _has("BadRequestError"), reason="LiteLLM class missing")
def test_bad_request_maps_to_4xx() -> None:
    exc = litellm.BadRequestError(message="bad request", model="gpt-4o", llm_provider="openai")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.ERROR_4XX


@pytest.mark.skipif(not _has("UnprocessableEntityError"), reason="LiteLLM class missing")
def test_unprocessable_entity_maps_to_4xx() -> None:
    exc = litellm.UnprocessableEntityError(
        message="invalid payload",
        model="gpt-4o",
        llm_provider="openai",
        response=_stub_response(422),
    )
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.ERROR_4XX


@pytest.mark.skipif(not _has("NotFoundError"), reason="LiteLLM class missing")
def test_not_found_maps_to_4xx() -> None:
    exc = litellm.NotFoundError(message="model not found", model="invalid", llm_provider="openai")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.ERROR_4XX


@pytest.mark.skipif(not _has("ContentPolicyViolationError"), reason="LiteLLM class missing")
def test_content_policy_maps_to_quality_failure() -> None:
    exc = litellm.ContentPolicyViolationError(
        message="filtered", model="gpt-4o", llm_provider="openai"
    )
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.QUALITY_FAILURE


@pytest.mark.skipif(not _has("ServiceUnavailableError"), reason="LiteLLM class missing")
def test_service_unavailable_maps_to_5xx() -> None:
    exc = litellm.ServiceUnavailableError(message="503", model="gpt-4o", llm_provider="openai")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.ERROR_5XX


@pytest.mark.skipif(not _has("InternalServerError"), reason="LiteLLM class missing")
def test_internal_server_error_maps_to_5xx() -> None:
    exc = litellm.InternalServerError(message="500", model="gpt-4o", llm_provider="openai")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.ERROR_5XX


def test_unknown_exception_falls_to_unknown() -> None:
    exc = RuntimeError("totally unrelated")
    assert normalize_litellm_error(exc).category == CanonicalErrorCategory.UNKNOWN


def test_canonical_error_carries_original_exception() -> None:
    exc = RuntimeError("trace this")
    canonical = normalize_litellm_error(exc)
    assert canonical.original_exception is exc
    assert canonical.provider_message == "trace this"
