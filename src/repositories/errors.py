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
