"""Mock adapter exception classes per spec 020 contracts.

These exceptions surface in tests that exercise the dispatch path
through the mock adapter (e.g., spec 015 breaker integration tests).
All four classes live here so consumers can catch them with a single
import.
"""

from __future__ import annotations

from src.api_bridge.adapter import CanonicalErrorCategory


class MockFixtureMissingError(Exception):
    """Raised when no fixture matches a dispatched input per FR-007.

    The exception names the missing fixture key (canonical hash + last-
    message substring) so the test author can see exactly what fixture
    needs to be added.
    """

    def __init__(self, canonical_hash: str, last_message_substring: str) -> None:
        self.canonical_hash = canonical_hash
        self.last_message_substring = last_message_substring
        super().__init__(
            "MockFixtureMissingError: no fixture matched. canonical_hash="
            f"{canonical_hash!r}, last_message_substring="
            f"{last_message_substring!r}"
        )


class MockInjectedError(Exception):
    """Raised by the mock adapter when an `errors` fixture entry matches.

    Carries the configured canonical category so the adapter's
    `normalize_error(exc)` can return a `CanonicalError` with the same
    semantics as the LiteLLM adapter would for an equivalent provider
    failure.
    """

    def __init__(
        self,
        category: CanonicalErrorCategory,
        provider_message: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.category = category
        self.provider_message = provider_message
        self.retry_after_seconds = retry_after_seconds
        super().__init__(provider_message or category.value)


class MockStreamingError(MockInjectedError):
    """Mid-stream injected error per contracts/stream-event-shape.md."""


class MockFixtureSchemaError(Exception):
    """Raised at adapter init when fixture-file shape fails schema validation."""
