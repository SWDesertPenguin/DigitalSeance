# SPDX-License-Identifier: AGPL-3.0-or-later

"""``accounts`` + ``account_participants`` repository for spec 023.

CRUD entry points backing the seven account-router endpoints:

- :meth:`create_account` — insert a fresh ``pending_verification`` row.
- :meth:`get_account_by_id` — primary-key lookup.
- :meth:`get_account_by_email_for_login` — case-insensitive lookup
  scoped to non-deleted statuses (returns ``None`` for both
  not-found AND deleted to keep the SC-005 timing path uniform).
- :meth:`update_account_email` — atomic email column update.
- :meth:`update_account_password_hash` — atomic password_hash update;
  also stamps ``updated_at = now()``.
- :meth:`mark_account_deleted` — zero email + password_hash, populate
  ``deleted_at`` + ``email_grace_release_at`` from
  ``SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS`` (FR-012, FR-013).
- :meth:`update_last_login_at` — stamp the column to ``now()``.
- :meth:`link_participant_to_account` — insert an
  ``account_participants`` join row (FR-002).
- :meth:`list_participants_for_account` — enumerate the join rows.

The ``/me/sessions`` query (research §9) lands in Phase 4 (T054).

See ``specs/023-user-accounts/data-model.md`` for the schema and the
cross-column application-side rules.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg

from src.models.account import Account, AccountParticipant
from src.repositories.base import BaseRepository

# Default grace period per contracts/env-vars.md; fallback when the
# env var is unset / empty. The validator already enforces [0, 365].
_DEFAULT_GRACE_DAYS = 7

# Status segmentation for the /me/sessions response (FR-008 + clarify
# Q7). "Live" covers active and paused — both are non-archived. The
# archived bucket holds only the literal 'archived' state today; future
# values like 'deleted' join it once spec 010 retention sweeps land.
_LIVE_STATUSES = ("active", "paused")
_ARCHIVED_STATUSES = ("archived",)


_LIST_SESSIONS_SQL = """
    SELECT s.id              AS session_id,
           s.name            AS name,
           s.created_at      AS last_activity_at,
           s.status          AS status,
           p.id              AS participant_id,
           p.role            AS role
    FROM account_participants ap
    JOIN participants p ON p.id = ap.participant_id
    JOIN sessions s     ON s.id = p.session_id
    WHERE ap.account_id = $1
      AND s.status = ANY($2::text[])
    ORDER BY s.created_at DESC
    LIMIT $3 OFFSET $4
"""


def _session_row_to_dict(record) -> dict:  # noqa: ANN001 — asyncpg.Record
    """Convert an SC-003 list-sessions row to the contract-shaped dict."""
    last_activity = record["last_activity_at"]
    return {
        "session_id": record["session_id"],
        "name": record["name"],
        "last_activity_at": last_activity.isoformat() if last_activity else None,
        "status": record["status"],
        "participant_id": record["participant_id"],
        "role": record["role"],
    }


def _read_grace_days() -> int:
    """Read SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS, falling back to default."""
    raw = os.environ.get("SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS", "")
    if raw == "":
        return _DEFAULT_GRACE_DAYS
    return int(raw)


class AccountRepository(BaseRepository):
    """Data access for the spec 023 ``accounts`` + ``account_participants`` tables."""

    async def create_account(
        self,
        *,
        email: str,
        password_hash: str,
        email_hash: str = "",
    ) -> Account:
        """Insert a fresh ``pending_verification`` account row.

        ``email`` is lower-cased application-side per research §2 — the
        partial unique index covers ``status IN ('pending_verification',
        'active')``, so a uniqueness violation here means a live or
        verifying account already owns the address. ``email_hash`` is
        the HMAC of the lowercased email computed by the caller (the
        repo doesn't read SACP_AUTH_LOOKUP_KEY); it's preserved across
        deletion so FR-013's grace lookup can match the deleted row.
        Default empty string keeps the column NOT NULL clean for direct
        repo tests that don't exercise the grace path.
        """
        new_id = uuid.uuid4()
        record = await self._fetch_one(
            """
            INSERT INTO accounts (id, email, email_hash, password_hash, status)
            VALUES ($1, $2, $3, $4, 'pending_verification')
            RETURNING *
            """,
            new_id,
            email.lower(),
            email_hash,
            password_hash,
        )
        if record is None:
            raise RuntimeError("create_account INSERT did not return a row")
        return Account.from_record(record)

    async def get_account_by_id(self, account_id: str) -> Account | None:
        """Primary-key lookup. Returns ``None`` if not found."""
        record = await self._fetch_one(
            "SELECT * FROM accounts WHERE id = $1",
            uuid.UUID(account_id),
        )
        return Account.from_record(record) if record is not None else None

    async def get_account_by_email_for_login(self, email: str) -> Account | None:
        """Case-insensitive lookup scoped to NON-deleted statuses.

        Returns ``None`` for both not-found AND deleted, so the
        SC-005 timing-resistance contract treats both branches
        identically. The login flow always runs argon2id verify even
        on miss (against a pinned dummy hash) to keep timing uniform.
        """
        record = await self._fetch_one(
            """
            SELECT * FROM accounts
            WHERE email = $1
              AND status IN ('pending_verification', 'active')
            """,
            email.lower(),
        )
        return Account.from_record(record) if record is not None else None

    async def is_email_grace_locked(self, email_hash: str) -> bool:
        """Return True if a deleted-status row reserves ``email_hash`` in grace.

        Implements FR-013: the deleted account row remains for audit
        linkage but reserves the email until ``email_grace_release_at``
        elapses. The lookup is by HMAC because the ``email`` column is
        zeroed at delete time per FR-012 — only ``email_hash`` survives.
        Re-registration during the window is refused with the generic
        ``registration_failed`` shape (no info leak about why).
        """
        if not email_hash:
            return False
        record = await self._fetch_one(
            """
            SELECT email_grace_release_at
            FROM accounts
            WHERE email_hash = $1
              AND status = 'deleted'
              AND email_grace_release_at IS NOT NULL
              AND email_grace_release_at > NOW()
            ORDER BY deleted_at DESC
            LIMIT 1
            """,
            email_hash,
        )
        return record is not None

    async def update_account_email(
        self,
        *,
        account_id: str,
        new_email: str,
    ) -> None:
        """Atomic email column update. Caller must have validated ownership."""
        await self._execute(
            """
            UPDATE accounts
            SET email = $1, updated_at = NOW()
            WHERE id = $2
            """,
            new_email.lower(),
            uuid.UUID(account_id),
        )

    async def update_account_password_hash(
        self,
        *,
        account_id: str,
        new_password_hash: str,
    ) -> None:
        """Atomic password_hash update; stamps ``updated_at`` to ``now()``."""
        await self._execute(
            """
            UPDATE accounts
            SET password_hash = $1, updated_at = NOW()
            WHERE id = $2
            """,
            new_password_hash,
            uuid.UUID(account_id),
        )

    async def mark_account_deleted(self, account_id: str) -> None:
        """Zero credentials + flip status to 'deleted' (FR-012, FR-013).

        Populates ``deleted_at`` to ``now()`` and
        ``email_grace_release_at`` to ``deleted_at + grace_days``,
        where ``grace_days`` reads from
        ``SACP_ACCOUNT_DELETION_EMAIL_GRACE_DAYS``. The ``email`` and
        ``password_hash`` columns become empty strings (NOT NULL stays
        clean; the partial unique index excludes deleted rows so the
        empty-string sentinel is fine to repeat across multiple
        deleted accounts).
        """
        grace_days = _read_grace_days()
        deleted_at = datetime.now(UTC)
        grace_release = deleted_at + timedelta(days=grace_days)
        await self._execute(
            """
            UPDATE accounts
            SET status = 'deleted',
                email = '',
                password_hash = '',
                deleted_at = $1,
                email_grace_release_at = $2,
                updated_at = NOW()
            WHERE id = $3
            """,
            deleted_at,
            grace_release,
            uuid.UUID(account_id),
        )

    async def update_last_login_at(self, account_id: str) -> None:
        """Stamp ``last_login_at`` to ``now()`` after a successful login."""
        await self._execute(
            "UPDATE accounts SET last_login_at = NOW() WHERE id = $1",
            uuid.UUID(account_id),
        )

    async def link_participant_to_account(
        self,
        *,
        account_id: str,
        participant_id: str,
    ) -> AccountParticipant:
        """Insert an ``account_participants`` join row (FR-002).

        ``participant_id`` is UNIQUE in the schema; an attempt to bind
        an already-bound participant raises
        :class:`asyncpg.UniqueViolationError` at the DB layer. Caller
        decides whether to surface that as a 409 or 422 to the API.
        """
        new_id = uuid.uuid4()
        record = await self._fetch_one(
            """
            INSERT INTO account_participants (id, account_id, participant_id)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            new_id,
            uuid.UUID(account_id),
            participant_id,
        )
        if record is None:
            raise RuntimeError("link_participant_to_account INSERT did not return a row")
        return AccountParticipant.from_record(record)

    async def list_participants_for_account(
        self,
        account_id: str,
    ) -> list[AccountParticipant]:
        """Return all join rows for the account, in insertion order."""
        records = await self._fetch_all(
            """
            SELECT * FROM account_participants
            WHERE account_id = $1
            ORDER BY created_at ASC
            """,
            uuid.UUID(account_id),
        )
        return [AccountParticipant.from_record(r) for r in records]

    async def list_sessions_for_account(
        self,
        *,
        account_id: str,
        archived: bool,
        offset: int,
        limit: int,
    ) -> list[dict]:
        """Return sessions an account has joined, segmented by archived state.

        Implements the FR-008 segmented response: `archived=False` returns
        live sessions (`status IN ('active', 'paused')`); `archived=True`
        returns archived ones. Ordered by ``sessions.created_at DESC``
        (used as the v1 last-activity proxy until a dedicated column
        lands per research §9). Each row carries the columns the
        contract enumerates: session_id, name, last_activity_at, role,
        participant_id, status.
        """
        statuses = _ARCHIVED_STATUSES if archived else _LIVE_STATUSES
        records = await self._fetch_all(
            _LIST_SESSIONS_SQL,
            uuid.UUID(account_id),
            list(statuses),
            int(limit),
            int(offset),
        )
        return [_session_row_to_dict(r) for r in records]

    async def count_sessions_for_account(self, account_id: str) -> int:
        """Total joined-session count for the FR-008 10K-threshold check."""
        record = await self._fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM account_participants
            WHERE account_id = $1
            """,
            uuid.UUID(account_id),
        )
        return int(record["n"]) if record is not None else 0

    async def find_binding_for_session(
        self,
        *,
        account_id: str,
        session_id: str,
    ) -> dict | None:
        """Look up the participant_id this account owns in a given session.

        Returns ``None`` if the account has no participant in the session
        (cross-account isolation enforced via ``account_id`` filter).
        Used by the rebind endpoint (FR-016) to bind the existing sid
        to the per-session participant credential.
        """
        record = await self._fetch_one(
            """
            SELECT p.id AS participant_id,
                   p.session_id AS session_id,
                   p.role AS role
            FROM account_participants ap
            JOIN participants p ON p.id = ap.participant_id
            WHERE ap.account_id = $1
              AND p.session_id = $2
            """,
            uuid.UUID(account_id),
            session_id,
        )
        if record is None:
            return None
        return {
            "participant_id": record["participant_id"],
            "session_id": record["session_id"],
            "role": record["role"],
        }

    async def transfer_participants(
        self,
        *,
        source_account_id: str,
        target_account_id: str,
    ) -> list[str]:
        """Repoint every account_participants row from source to target.

        Returns the participant_id list that moved. Implements the data
        side of FR-020 ownership transfer; the admin-auth boundary is
        enforced at the route layer. The schema's
        ``UNIQUE(participant_id)`` is preserved (one participant still
        belongs to at most one account); the operation is atomic at the
        SQL UPDATE level.
        """
        records = await self._fetch_all(
            """
            UPDATE account_participants
            SET account_id = $1
            WHERE account_id = $2
            RETURNING participant_id
            """,
            uuid.UUID(target_account_id),
            uuid.UUID(source_account_id),
        )
        return [r["participant_id"] for r in records]


def make_account_repository(pool: asyncpg.Pool) -> AccountRepository:
    """Factory used by the FastAPI app's lifespan to construct the repository."""
    return AccountRepository(pool)
