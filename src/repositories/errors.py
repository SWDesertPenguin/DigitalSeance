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


class IPBindingMismatchError(ValueError):
    """Token valid but client IP does not match bound IP."""
