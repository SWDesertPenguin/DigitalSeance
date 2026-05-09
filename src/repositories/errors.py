# SPDX-License-Identifier: AGPL-3.0-or-later

"""Domain error types for repository operations."""

from __future__ import annotations


class EncryptionKeyMissingError(RuntimeError):
    """SACP_ENCRYPTION_KEY not set — fail closed."""


class SessionNotActiveError(ValueError):
    """Operation requires an active session."""


class InvalidTransitionError(ValueError):
    """Illegal session status transition."""


class DuplicateVoteError(ValueError):
    """Participant already voted on this proposal."""


class InviteExpiredError(ValueError):
    """Invite token past expiry timestamp."""


class InviteExhaustedError(ValueError):
    """Invite token max uses reached."""


class TokenExpiredError(ValueError):
    """Auth token past expiry timestamp."""


class TokenInvalidError(ValueError):
    """Auth token hash does not match any participant."""


class AuthRequiredError(ValueError):
    """No auth token provided."""


class NotFacilitatorError(PermissionError):
    """Caller lacks facilitator role for this operation."""


class ParticipantNotInSessionError(LookupError):
    """Target participant id does not belong to the session."""


class IPBindingMismatchError(ValueError):
    """Token valid but client IP does not match bound IP."""


class AllParticipantsExhaustedError(RuntimeError):
    """Every participant is paused, over-budget, or circuit-broken."""


class ProviderDispatchError(RuntimeError):
    """LiteLLM provider call failed after retries."""


class ContextWindowOverflowError(ProviderDispatchError):
    """Provider rejected the request because it exceeded the model's context window.

    Distinct from generic dispatch failures so RoutingLog can record
    the failure mode and operators can see overshoots in shakedowns
    without grepping error strings. Subclasses ProviderDispatchError
    so existing `except ProviderDispatchError` paths keep working.
    """


class CompoundRetryExhaustedError(ProviderDispatchError):
    """Cumulative dispatch+retry elapsed reached the FR-031 hard cap.

    Distinct from generic dispatch failures so RoutingLog can record
    `reason='compound_retry_exhausted'` and operators can alert on the
    actionable subset (per runbook §6.4) rather than the umbrella
    `provider_error` bucket. Subclasses ProviderDispatchError so existing
    handlers keep working.
    """


class ResponseQualityError(ValueError):
    """AI response failed quality checks (empty, duplicate, repetitive)."""


class BudgetExceededError(ValueError):
    """Turn would exceed participant's budget ceiling."""
