# SPDX-License-Identifier: AGPL-3.0-or-later

"""Account + AccountParticipant value types for spec 023.

Frozen dataclasses returned by the account repository. Field shape
matches the alembic 015 schema documented in
``specs/023-user-accounts/data-model.md``. Plain dataclasses (not
pydantic) keep the dependency surface flat — pydantic validation is
used only at the FastAPI request boundary, not for internal value
types per Constitution V11.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

AccountStatus = Literal["pending_verification", "active", "deleted"]


@dataclass(frozen=True, slots=True)
class Account:
    """One row of the ``accounts`` table.

    The ``email`` and ``password_hash`` fields are empty strings when
    ``status == 'deleted'`` per FR-012 + research §2 (the row stays
    for audit linkage; credentials are zeroed). ``deleted_at`` and
    ``email_grace_release_at`` are populated together at deletion time.
    """

    id: str
    email: str
    password_hash: str
    status: AccountStatus
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None
    email_grace_release_at: datetime | None

    @classmethod
    def from_record(cls, record: Any) -> Account:
        """Construct an Account from an asyncpg Record (or dict-like).

        UUID columns surface as ``uuid.UUID`` instances from asyncpg;
        we coerce to ``str`` so the value type stays JSON-friendly and
        the ID format matches the rest of the codebase's text-UUID
        convention.
        """
        return cls(
            id=str(record["id"]),
            email=record["email"],
            password_hash=record["password_hash"],
            status=record["status"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            last_login_at=record["last_login_at"],
            deleted_at=record["deleted_at"],
            email_grace_release_at=record["email_grace_release_at"],
        )


@dataclass(frozen=True, slots=True)
class AccountParticipant:
    """One row of the ``account_participants`` join table.

    ``account_id`` is preserved when the parent account flips to
    ``status='deleted'`` (FK is ON DELETE RESTRICT per FR-012).
    ``participant_id`` is unique per FR-002 — a participant belongs
    to at most one account.
    """

    id: str
    account_id: str
    participant_id: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> AccountParticipant:
        return cls(
            id=str(record["id"]),
            account_id=str(record["account_id"]),
            participant_id=record["participant_id"],
            created_at=record["created_at"],
        )
