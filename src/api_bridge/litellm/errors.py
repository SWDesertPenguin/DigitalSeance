# SPDX-License-Identifier: AGPL-3.0-or-later

"""LiteLLM exception -> CanonicalError mapping per spec 020 contract.

Implements the static authoritative table in
`specs/020-provider-adapter-abstraction/contracts/canonical-error-mapping.md`.
Spec 015's circuit breaker depends on stable category assignment per
FR-008; the fallback `UNKNOWN` category catches any LiteLLM exception
class missing from the table so the system continues to function.
"""

from __future__ import annotations

import litellm

from src.api_bridge.adapter import CanonicalError, CanonicalErrorCategory

# Order matters: ContentPolicyViolationError inherits from BadRequestError,
# so QUALITY_FAILURE MUST precede ERROR_4XX or the parent-class match
# would short-circuit and lose the spec-015 FR-008 distinction.
_CATEGORY_RULES: tuple[tuple[tuple[str, ...], CanonicalErrorCategory], ...] = (
    (("AuthenticationError", "PermissionDeniedError"), CanonicalErrorCategory.AUTH_ERROR),
    (("Timeout", "APIConnectionError"), CanonicalErrorCategory.TIMEOUT),
    (("ContentPolicyViolationError",), CanonicalErrorCategory.QUALITY_FAILURE),
    (
        (
            "ContextWindowExceededError",
            "BadRequestError",
            "UnprocessableEntityError",
            "NotFoundError",
        ),
        CanonicalErrorCategory.ERROR_4XX,
    ),
    (("ServiceUnavailableError", "InternalServerError"), CanonicalErrorCategory.ERROR_5XX),
)


def normalize_litellm_error(exc: BaseException) -> CanonicalError:
    """Map a LiteLLM exception to the canonical seven-category enum."""
    if isinstance(exc, litellm.RateLimitError):
        return CanonicalError(
            category=CanonicalErrorCategory.RATE_LIMIT,
            retry_after_seconds=_coerce_retry_after(getattr(exc, "retry_after", None)),
            original_exception=exc,
            provider_message=str(exc),
        )
    for class_names, category in _CATEGORY_RULES:
        classes = _safe_class_tuple(litellm, class_names)
        if classes and isinstance(exc, classes):
            return CanonicalError(
                category=category, original_exception=exc, provider_message=str(exc)
            )
    return CanonicalError(
        category=CanonicalErrorCategory.UNKNOWN,
        original_exception=exc,
        provider_message=str(exc),
    )


def _coerce_retry_after(raw: object) -> int | None:
    """Coerce a LiteLLM retry_after attr to int seconds, or None on bad input."""
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _safe_class_tuple(module: object, names: tuple[str, ...]) -> tuple[type, ...] | None:
    """Resolve `names` on `module`; return as a tuple of types, skipping missing.

    LiteLLM's exception hierarchy has changed names across releases
    (`UnprocessableEntityError` etc. are present from v1.30+). Reading
    by name with `getattr` keeps the mapping resilient to vendor renames
    without breaking the test suite when an older / newer LiteLLM is
    pinned.
    """
    classes: list[type] = []
    for name in names:
        cls = getattr(module, name, None)
        if isinstance(cls, type):
            classes.append(cls)
    return tuple(classes) if classes else None
