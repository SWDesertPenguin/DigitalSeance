# SPDX-License-Identifier: AGPL-3.0-or-later

"""Account-service orchestration for spec 023.

Implements the create + verify + login flow (US1, T044-T046) plus the
password-change SessionStore invalidation hook (US3, T049). The four
US3-only entry points (request_email_change / confirm_email_change /
delete_account / list_sessions) land in Phase 4 / 5 alongside their
own tests; the matching ``account_routes`` endpoints stub them as 501
until then (T047 stub block).

Design choices:

- The service constructs its own ``PasswordHasher`` and reads the
  pinned dummy hash at import time so the SC-005 timing-uniform login
  path doesn't pay a per-request dummy-hash cost. The dummy is
  produced by the same hasher used for real verification so its
  parameters match — argon2's CPU cost is the SC-005 contract, not
  the value of the plaintext.
- Audit rows go through ``LogRepository.log_admin_action`` (the
  established lane-pattern; lane C's prior drift catch). Account
  events have no natural ``session_id`` / ``facilitator_id`` tuple,
  so we use the ``_account_<account_id>`` sentinel for ``session_id``
  and the account_id (or ``"_system"`` for pre-auth events) for
  ``facilitator_id``. The denormalized TEXT-only schema (alembic 007)
  permits this — no FK enforcement applies.
- Verification codes are looked up by HMAC hash against the
  ``account_verification_emitted`` rows. The "consumed" check joins
  for an existing ``account_verification_consumed`` row carrying the
  same emit-row id; absence means unconsumed.

Cross-references:

- Spec 023 ``contracts/account-endpoints.md`` — endpoint payload shape.
- Spec 023 ``contracts/audit-log-events.md`` — audit-row shape per
  action.
- Spec 023 ``research.md`` §1 (argon2id), §3 (codes), §5 (rate
  limiter), §10 (SessionStore extension).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.accounts.codes import (
    AccountCode,
    hash_code,
    make_email_change_code,
    make_verification_code,
)
from src.accounts.email_transport import EmailTransport, NoopEmailTransport
from src.accounts.hashing import PasswordHasher
from src.accounts.rate_limit import LoginRateLimiter, RateLimitExceeded
from src.repositories.account_repo import AccountRepository

if TYPE_CHECKING:
    from src.repositories.log_repo import LogRepository
    from src.web_ui.session_store import SessionStore

log = logging.getLogger(__name__)

# Email syntax validator. RFC 5321 is a 320-character pure-pedantic
# spec; the V13 use cases want a "looks like an email" gate, not a
# parser. Mirrors the v1-pragmatic regex used elsewhere in the
# codebase: local-part + ``@`` + domain with at least one dot and
# non-zero TLD length.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Password length envelope per contracts/account-endpoints.md.
_PASSWORD_MIN_LEN = 12
_PASSWORD_MAX_LEN = 1024

# Sentinel used as ``session_id`` on account-level audit rows; the
# admin_audit_log columns are TEXT-only (alembic 007) so this is
# safe. Operators querying the audit log filter on this prefix to
# isolate account events.
_ACCOUNT_AUDIT_SESSION_PREFIX = "_account_"
_SYSTEM_FACILITATOR = "_system"

# FR-008: structured WARN + audit row when an account's joined-session
# count crosses this threshold. Cursor pagination is a backlog item
# the warning announces; the offset path keeps working past it.
_SESSION_COUNT_THRESHOLD = 10_000


def _next_offset_or_none(current_offset: int, page_size: int, page_count: int) -> int | None:
    """Return the offset for the next page or None when the segment is exhausted."""
    if page_count < page_size:
        return None
    return current_offset + page_size


class AccountServiceError(Exception):
    """Base class for service-layer business-rule violations.

    Carries an ``error_code`` (matches contracts/account-endpoints.md
    error_code values) and an ``http_status`` so the route layer
    translates without hardcoding the mapping.
    """

    def __init__(self, *, error_code: str, http_status: int, message: str = "") -> None:
        self.error_code = error_code
        self.http_status = http_status
        super().__init__(message or error_code)


@dataclass(frozen=True)
class CreateAccountResult:
    """Returned from :meth:`AccountService.create_account`."""

    account_id: str
    status: str
    verification_email_sent: bool
    # Plaintext code is RETURNED to the caller (route layer) only when the
    # noop transport is in play AND the operator has opted into dev
    # leak — kept None by default so production noop transport uses the
    # audit-log-only flow. The route layer never echoes this to the HTTP
    # response.
    dev_plaintext_code: str | None = None


@dataclass(frozen=True)
class LoginResult:
    """Returned from :meth:`AccountService.login`. ``sid`` minted via
    SessionStore; the route layer wraps it in the signed cookie."""

    account_id: str
    sid: str
    rehash_performed: bool


def _hmac_email(email: str) -> str:
    """HMAC-SHA256 of the lower-cased email. Same key as :mod:`codes`.

    Used in audit-row payloads so cross-account-isolation lookups can
    JOIN by hash without storing plaintext emails in the audit log
    (FR-014 + contracts/audit-log-events.md ScrubFilter rules).
    """
    key = os.environ.get("SACP_AUTH_LOOKUP_KEY", "")
    if not key:
        raise RuntimeError(
            "SACP_AUTH_LOOKUP_KEY is required to hash emails for audit rows; "
            "the V16 validator should have rejected an empty value at startup."
        )
    return hmac.new(
        key.encode("utf-8"),
        email.lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class AccountService:
    """Orchestrates the account-router endpoints for spec 023.

    Constructor injection rather than module-level globals — the
    FastAPI app's lifespan builds one instance and attaches it to
    ``app.state.account_service``. Tests construct their own with
    test doubles for the email transport / log repo / session store.

    The internal :class:`PasswordHasher` is shared across all calls;
    constructing a new hasher per request would multiply the argon2id
    parameter-read cost. The pinned dummy hash is computed once at
    init so the SC-005 timing-uniform login path is constant-time
    on the email-miss branch.
    """

    def __init__(
        self,
        *,
        account_repo: AccountRepository,
        log_repo: LogRepository,
        session_store: SessionStore,
        email_transport: EmailTransport | None = None,
        rate_limiter: LoginRateLimiter | None = None,
        hasher: PasswordHasher | None = None,
    ) -> None:
        self._account_repo = account_repo
        self._log_repo = log_repo
        self._session_store = session_store
        self._hasher = hasher if hasher is not None else PasswordHasher()
        self._rate_limiter = rate_limiter if rate_limiter is not None else LoginRateLimiter()
        # Default to the noop adapter when no real transport is wired.
        # The factory at startup typically passes a NoopEmailTransport
        # bound to the audit-row writer so misses aren't silent.
        self._email_transport = (
            email_transport if email_transport is not None else NoopEmailTransport()
        )
        # Pinned dummy hash for SC-005 timing-uniform login (email-miss
        # path). Computed once so per-request cost is verify-only.
        self._dummy_hash = self._hasher.hash("__sacp_login_dummy_v1__")
        # FR-008 idempotency set: account_ids whose 10K-threshold trip
        # has already emitted within this process lifetime. Keeps the
        # WARN + audit row from spamming on every call once tripped.
        self._threshold_emitted_today: set[str] = set()

    # ------------------------------------------------------------------
    # T044: create_account
    # ------------------------------------------------------------------

    async def create_account(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
    ) -> CreateAccountResult:
        """Create a fresh account in ``pending_verification`` status (FR-005).

        Validation order matches contracts/account-endpoints.md: rate
        limit -> email syntax -> password length -> uniqueness. Each
        branch raises :class:`AccountServiceError`; the route layer is
        a thin translator. Side effects: argon2id-hashed account row,
        ``account_create`` + ``account_verification_emitted`` audit
        rows, transport call. Transport failure does NOT roll back —
        operator recovers via the audit log per the spec edge case.
        """
        await self._enforce_rate_limit(client_ip)
        self._validate_email_syntax(email)
        self._validate_password_length(password)
        if await self._account_repo.is_email_grace_locked(email):
            raise AccountServiceError(
                error_code="registration_failed",
                http_status=409,
                message="email reserved by grace period",
            )
        account = await self._insert_account_row(email=email, password=password)
        await self._emit_account_create_audit(
            account_id=account.id, email=email, client_ip=client_ip
        )
        code = make_verification_code()
        await self._emit_verification_code_audit(account_id=account.id, code=code)
        verification_email_sent = await self._send_verification_email(
            account_id=account.id, to_email=email, code=code
        )
        return CreateAccountResult(
            account_id=account.id,
            status=account.status,
            verification_email_sent=verification_email_sent,
            dev_plaintext_code=self._dev_plaintext_for(code),
        )

    async def _insert_account_row(self, *, email: str, password: str):  # noqa: ANN202 — Account
        """Hash password + INSERT row; translate uniqueness collisions."""
        password_hash = self._hasher.hash(password)
        try:
            return await self._account_repo.create_account(email=email, password_hash=password_hash)
        except Exception as exc:  # noqa: BLE001 — uniqueness collisions translate
            # asyncpg.UniqueViolationError surfaces as the partial
            # unique index trip; map to a generic registration_failed
            # so the response body doesn't leak whether the email is
            # already registered (clarify Q11 + FR-014 spirit).
            if "UniqueViolationError" in type(exc).__name__:
                raise AccountServiceError(
                    error_code="registration_failed",
                    http_status=409,
                    message="account creation failed",
                ) from exc
            raise

    @staticmethod
    def _dev_plaintext_for(code: AccountCode) -> str | None:
        """Surface plaintext code only when noop transport is in use.

        The route layer NEVER echoes this in the HTTP response — it's
        the internal hand-off so ops scripts can pluck the code from
        the in-process result rather than parsing audit rows.
        """
        if os.environ.get("SACP_EMAIL_TRANSPORT", "noop") == "noop":
            return code.plaintext
        return None

    # ------------------------------------------------------------------
    # T045: verify_account
    # ------------------------------------------------------------------

    async def verify_account(
        self,
        *,
        account_id: str,
        code: str,
    ) -> str:
        """Consume a verification code and flip the account to active (FR-006).

        Lookups go through the HMAC hash (the plaintext code is never
        stored). The "unconsumed" check looks for an
        ``account_verification_emitted`` row with no matching
        ``account_verification_consumed`` row — research §3. Returns
        the new status string ('active'); raises
        ``invalid_or_expired_code`` on any failure path so the
        response stays generic.
        """
        emit_row = await self._resolve_unconsumed_emit_row(account_id=account_id, code=code)
        # Flip status + write the consumed audit row in lockstep so
        # a partial failure leaves the system either fully unflipped
        # or fully consumed; the repo and audit writer share the
        # same connection pool but separate transactions today.
        await self._account_repo._execute(  # noqa: SLF001 — repo helper, owned by us
            "UPDATE accounts SET status = 'active', updated_at = NOW() WHERE id = $1",
            self._uuid(account_id),
        )
        await self._emit_verification_consumed_audit(
            account_id=account_id, emit_row_id=str(emit_row["id"])
        )
        return "active"

    async def _resolve_unconsumed_emit_row(
        self,
        *,
        account_id: str,
        code: str,
    ) -> dict:
        """Validate + resolve an emit row, raising the generic 400 on miss."""
        if len(code) != 16:
            raise AccountServiceError(
                error_code="invalid_or_expired_code",
                http_status=400,
                message="code length mismatch",
            )
        account = await self._account_repo.get_account_by_id(account_id)
        if account is None or account.status != "pending_verification":
            raise AccountServiceError(
                error_code="invalid_or_expired_code",
                http_status=400,
                message="account not in pending_verification",
            )
        emit_row = await self._lookup_unconsumed_emit_row(
            account_id=account_id, code_hash=hash_code(code)
        )
        if emit_row is None:
            raise AccountServiceError(
                error_code="invalid_or_expired_code",
                http_status=400,
                message="no unconsumed emit row matches",
            )
        return emit_row

    # ------------------------------------------------------------------
    # T046: login (SC-005 timing-uniform + SC-007 transparent re-hash)
    # ------------------------------------------------------------------

    async def login(
        self,
        *,
        email: str,
        password: str,
        client_ip: str,
    ) -> LoginResult:
        """Authenticate an account by email + password (FR-007).

        Order: rate-limit (FR-015) -> email lookup (case-insensitive,
        deleted-excluded) -> argon2id verify ALWAYS (real hash on hit,
        pinned dummy on miss for SC-005 timing equality) -> active
        check -> SC-007 transparent re-hash -> SessionStore.create +
        last_login_at + audit row. Failure paths all raise generic
        ``invalid_credentials`` 401 (no info leak).
        """
        await self._login_rate_limit_or_audit(email=email, client_ip=client_ip)
        start = datetime.now(UTC)
        account = await self._account_repo.get_account_by_email_for_login(email)
        if account is None:
            await self._login_miss_path(
                password=password, email=email, client_ip=client_ip, start=start
            )
        if not self._hasher.verify(account.password_hash, password) or account.status != "active":
            await self._emit_login_failed_audit(
                email=email,
                client_ip=client_ip,
                failure_reason="invalid_credentials",
                elapsed_ms=self._elapsed_ms(start),
            )
            raise AccountServiceError(
                error_code="invalid_credentials",
                http_status=401,
                message="password verify failed or status inactive",
            )
        rehash_performed = await self._maybe_rehash(account=account, password=password)
        return await self._finalize_login(
            account=account,
            client_ip=client_ip,
            rehash_performed=rehash_performed,
        )

    async def _login_rate_limit_or_audit(
        self,
        *,
        email: str,
        client_ip: str,
    ) -> None:
        """Run the per-IP rate limiter; emit failed-audit on trip."""
        try:
            await self._enforce_rate_limit(client_ip)
        except AccountServiceError:
            await self._emit_login_failed_audit(
                email=email,
                client_ip=client_ip,
                failure_reason="rate_limit_exceeded",
                elapsed_ms=0,
            )
            raise

    async def _login_miss_path(
        self,
        *,
        password: str,
        email: str,
        client_ip: str,
        start: datetime,
    ) -> None:
        """SC-005 timing-uniform email-miss branch — always raises 401."""
        # SC-005: ALWAYS run verify, even on miss. The dummy is pinned
        # at init so its parameters match the real hasher's; argon2's
        # CPU cost is the SC-005 contract.
        self._hasher.verify(self._dummy_hash, password)
        await self._emit_login_failed_audit(
            email=email,
            client_ip=client_ip,
            failure_reason="invalid_credentials",
            elapsed_ms=self._elapsed_ms(start),
        )
        raise AccountServiceError(
            error_code="invalid_credentials",
            http_status=401,
            message="email lookup miss",
        )

    async def _maybe_rehash(self, *, account, password: str) -> bool:  # noqa: ANN001 — Account
        """SC-007 transparent re-hash on parameter change.

        Re-hashes the submitted plaintext under current parameters and
        UPDATES ``accounts.password_hash``. Failure of the rehash is
        non-fatal — the login still succeeds; the next login retries.
        """
        if not self._hasher.needs_rehash(account.password_hash):
            return False
        try:
            new_hash = self._hasher.hash(password)
            await self._account_repo.update_account_password_hash(
                account_id=account.id, new_password_hash=new_hash
            )
            return True
        except Exception:  # noqa: BLE001 — rehash failure is non-fatal
            log.warning(
                "argon2id transparent re-hash failed for account %s; " "next login will retry",
                account.id,
                exc_info=True,
            )
            return False

    async def _finalize_login(
        self,
        *,
        account,  # noqa: ANN001 — Account
        client_ip: str,
        rehash_performed: bool,
    ) -> LoginResult:
        """Mint sid, stamp last_login_at, emit audit row."""
        sid = await self._session_store.create(account_id=account.id)
        await self._account_repo.update_last_login_at(account.id)
        await self._emit_account_login_audit(
            account_id=account.id,
            client_ip=client_ip,
            rehash_performed=rehash_performed,
        )
        return LoginResult(
            account_id=account.id,
            sid=sid,
            rehash_performed=rehash_performed,
        )

    # ------------------------------------------------------------------
    # T054 + T055 + T057: /me/sessions list + rebind (US2)
    # ------------------------------------------------------------------

    async def list_sessions(
        self,
        *,
        account_id: str,
        active_offset: int = 0,
        archived_offset: int = 0,
        page_size: int = 50,
    ) -> dict:
        """Return the segmented session list for ``GET /me/sessions``.

        FR-008: ``{active_sessions, archived_sessions}`` segmented;
        ordered by last-activity-at DESC within each segment;
        offset-paginated at 50/page per segment. The 10K-threshold
        warning trips when the joined-session count crosses
        ``_SESSION_COUNT_THRESHOLD``; idempotent per (account_id, day)
        via dedup on the audit-row's date prefix.
        """
        active = await self._account_repo.list_sessions_for_account(
            account_id=account_id,
            archived=False,
            offset=active_offset,
            limit=page_size,
        )
        archived = await self._account_repo.list_sessions_for_account(
            account_id=account_id,
            archived=True,
            offset=archived_offset,
            limit=page_size,
        )
        await self._maybe_emit_count_threshold(account_id=account_id)
        return {
            "active_sessions": active,
            "archived_sessions": archived,
            "active_next_offset": _next_offset_or_none(active_offset, page_size, len(active)),
            "archived_next_offset": _next_offset_or_none(archived_offset, page_size, len(archived)),
        }

    async def _maybe_emit_count_threshold(self, *, account_id: str) -> None:
        """FR-008 10K-threshold trip: structured WARN + audit row, idempotent."""
        count = await self._account_repo.count_sessions_for_account(account_id)
        if count <= _SESSION_COUNT_THRESHOLD:
            return
        if account_id in self._threshold_emitted_today:
            return
        self._threshold_emitted_today.add(account_id)
        log.warning(
            "spec 023 FR-008: account %s joined-session count %s exceeds "
            "%s; cursor pagination is a backlog item",
            account_id,
            count,
            _SESSION_COUNT_THRESHOLD,
        )
        payload = {
            "account_id": account_id,
            "count": count,
            "threshold": _SESSION_COUNT_THRESHOLD,
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_session_count_threshold_tripped",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def rebind_to_session(
        self,
        *,
        account_id: str,
        session_id: str,
        sid: str,
    ) -> dict:
        """Bind the account-cookie sid to a per-session participant.

        FR-016 + research §10: the existing SessionEntry stays (single
        sid per cookie); we just populate the participant_id +
        session_id fields so subsequent participant-flow calls succeed.
        Returns ``{session_id, participant_id, rebound: bool}`` or
        raises ``not_found`` if the account doesn't own a participant
        in the requested session (no info leak per FR-009).
        """
        binding = await self._account_repo.find_binding_for_session(
            account_id=account_id,
            session_id=session_id,
        )
        if binding is None:
            raise AccountServiceError(
                error_code="not_found",
                http_status=404,
                message="account does not own a participant in that session",
            )
        await self._session_store.rebind_account_session(
            sid=sid,
            participant_id=binding["participant_id"],
            session_id=binding["session_id"],
        )
        return {
            "session_id": binding["session_id"],
            "participant_id": binding["participant_id"],
            "rebound": True,
        }

    # ------------------------------------------------------------------
    # T064: change_password (US3) — invalidates non-actor sids + audit
    # ------------------------------------------------------------------

    async def change_password(
        self,
        *,
        account_id: str,
        current_password: str,
        new_password: str,
        current_sid: str,
    ) -> int:
        """Change the account password and invalidate non-actor sids.

        FR-011 / clarify Q12 — the actor's current sid SURVIVES; every
        other sid for the account is dropped from the SessionStore
        so other browsers force a re-login on the next request that
        consults the store. Returns the count of sids dropped and
        emits the ``account_password_change`` audit row.
        """
        account = await self._require_active_account(account_id)
        self._validate_password_length(new_password)
        if not self._hasher.verify(account.password_hash, current_password):
            raise AccountServiceError(
                error_code="invalid_credentials",
                http_status=401,
                message="current password mismatch",
            )
        new_hash = self._hasher.hash(new_password)
        await self._account_repo.update_account_password_hash(
            account_id=account_id,
            new_password_hash=new_hash,
        )
        dropped = await self._session_store.delete_other_sids_for_account(
            account_id,
            except_sid=current_sid,
        )
        await self._emit_password_change_audit(
            account_id=account_id, other_sessions_invalidated=dropped
        )
        return dropped

    # ------------------------------------------------------------------
    # T063: email change — notify-old + verify-new (clarify Q11)
    # ------------------------------------------------------------------

    async def request_email_change(
        self,
        *,
        account_id: str,
        new_email: str,
    ) -> dict:
        """Emit verification to NEW + heads-up to OLD email (clarify Q11).

        Persists the pending change in an ``account_email_change_emitted``
        audit row whose payload carries the new_email; the actual
        ``accounts.email`` UPDATE happens on confirm. Refuses if the new
        email collides with an existing active or grace-window account
        (registration_failed shape, generic).
        """
        account = await self._require_active_account(account_id)
        self._validate_email_syntax(new_email)
        await self._reject_if_email_taken(new_email)
        code = make_email_change_code()
        await self._emit_email_change_code_audit(
            account_id=account_id, code=code, new_email=new_email
        )
        await self._send_email_change_emails(
            account_id=account_id,
            old_email=account.email,
            new_email=new_email,
            code=code,
        )
        await self._emit_email_change_old_notified_audit(
            account_id=account_id, old_email=account.email
        )
        return {"verification_email_sent": True, "old_email_notified": True}

    async def confirm_email_change(self, *, account_id: str, code: str) -> dict:
        """Consume the email-change code and apply the new email."""
        await self._require_active_account(account_id)
        emit_row = await self._lookup_unconsumed_email_change_row(account_id=account_id, code=code)
        if emit_row is None:
            raise AccountServiceError(
                error_code="invalid_or_expired_code",
                http_status=400,
                message="email change code missing or expired",
            )
        new_email = json.loads(emit_row["new_value"]).get("new_email")
        await self._account_repo.update_account_email(
            account_id=account_id,
            new_email=new_email,
        )
        await self._emit_email_change_consumed_audit(
            account_id=account_id, emit_row_id=str(emit_row["id"])
        )
        return {"email_changed": True, "new_email": new_email}

    # ------------------------------------------------------------------
    # T065: account deletion (FR-012, FR-013)
    # ------------------------------------------------------------------

    async def delete_account(self, *, account_id: str, current_password: str) -> dict:
        """Zero credentials, reserve email per grace window, emit export."""
        account = await self._require_active_account(account_id)
        if not self._hasher.verify(account.password_hash, current_password):
            raise AccountServiceError(
                error_code="invalid_credentials",
                http_status=401,
                message="current password mismatch",
            )
        export_sent = await self._send_delete_export_email(
            account_id=account_id, to_email=account.email
        )
        await self._account_repo.mark_account_deleted(account_id)
        await self._session_store.delete_all_sids_for_account(account_id)
        await self._emit_account_delete_audit(account_id=account_id, export_sent=export_sent)
        post = await self._account_repo.get_account_by_id(account_id)
        return {
            "account_id": account_id,
            "status": "deleted",
            "export_email_sent": export_sent,
            "email_grace_release_at": (
                post.email_grace_release_at.isoformat()
                if post is not None and post.email_grace_release_at is not None
                else None
            ),
        }

    async def _require_active_account(self, account_id: str):  # noqa: ANN202 — Account
        """Resolve + status='active' check; raises ``not_authenticated`` 401."""
        account = await self._account_repo.get_account_by_id(account_id)
        if account is None or account.status != "active":
            raise AccountServiceError(
                error_code="not_authenticated",
                http_status=401,
                message="account not active",
            )
        return account

    async def _reject_if_email_taken(self, new_email: str) -> None:
        """Refuse if NEW email is taken by an active or grace-window account."""
        existing = await self._account_repo.get_account_by_email_for_login(new_email)
        if existing is not None:
            raise AccountServiceError(
                error_code="email_change_failed",
                http_status=409,
                message="new email already registered",
            )

    async def _send_email_change_emails(
        self,
        *,
        account_id: str,
        old_email: str,
        new_email: str,
        code: AccountCode,
    ) -> None:
        """Emit verification to NEW + informational notice to OLD."""
        try:
            await self._email_transport.send(
                to=new_email,
                subject="Confirm your new SACP email",
                body=f"Your verification code: {code.plaintext}",
                purpose="email_change_new",
            )
        except Exception:  # noqa: BLE001 — transport miss recoverable via audit log
            log.warning("email_change new-email transport miss for %s", account_id)
        try:
            await self._email_transport.send(
                to=old_email,
                subject="Heads-up: someone is changing your SACP email",
                body="Informational notice — no action required.",
                purpose="email_change_old_notify",
            )
        except Exception:  # noqa: BLE001 — transport miss recoverable via audit log
            log.warning("email_change old-email transport miss for %s", account_id)

    async def _send_delete_export_email(
        self,
        *,
        account_id: str,
        to_email: str,
    ) -> bool:
        """Emit the spec 010 debug-export to the registered email."""
        try:
            await self._email_transport.send(
                to=to_email,
                subject="Your SACP account export",
                body=f"Account {account_id} export (placeholder; spec 010 wire-up).",
                purpose="account_delete_export",
            )
            return True
        except Exception:  # noqa: BLE001 — deletion proceeds even on transport miss
            log.warning("delete-export transport miss for %s", account_id, exc_info=True)
            return False

    async def _lookup_unconsumed_email_change_row(
        self,
        *,
        account_id: str,
        code: str,
    ) -> dict | None:
        rows = await self._account_repo._fetch_all(  # noqa: SLF001 — owned helper
            _LOOKUP_EMAIL_CHANGE_SQL,
            self._audit_session_id(account_id),
            account_id,
        )
        return self._first_matching_emit_row(rows=rows, code_hash=hash_code(code))

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_email_syntax(self, email: str) -> None:
        if not _EMAIL_RE.match(email):
            raise AccountServiceError(
                error_code="email_invalid",
                http_status=422,
                message="email syntax invalid",
            )

    def _validate_password_length(self, password: str) -> None:
        n = len(password)
        if n < _PASSWORD_MIN_LEN:
            raise AccountServiceError(
                error_code="password_too_short",
                http_status=422,
                message=f"password length {n} below minimum {_PASSWORD_MIN_LEN}",
            )
        if n > _PASSWORD_MAX_LEN:
            raise AccountServiceError(
                error_code="password_too_long",
                http_status=422,
                message=f"password length {n} above maximum {_PASSWORD_MAX_LEN}",
            )

    async def _enforce_rate_limit(self, client_ip: str) -> None:
        try:
            await self._rate_limiter.check(client_ip)
        except RateLimitExceeded as exc:
            raise AccountServiceError(
                error_code="rate_limit_exceeded",
                http_status=429,
                message=f"retry_after={exc.retry_after_seconds}",
            ) from exc

    @staticmethod
    def _elapsed_ms(start: datetime) -> int:
        delta = datetime.now(UTC) - start
        return int(delta.total_seconds() * 1000)

    @staticmethod
    def _uuid(account_id: str) -> object:
        import uuid as _uuid

        return _uuid.UUID(account_id)

    # ------------------------------------------------------------------
    # Audit-row writers — encode payloads in `new_value` JSON
    # ------------------------------------------------------------------

    @staticmethod
    def _audit_session_id(account_id: str) -> str:
        """Return the synthetic audit-log session_id for this account."""
        return f"{_ACCOUNT_AUDIT_SESSION_PREFIX}{account_id}"

    async def _emit_account_create_audit(
        self,
        *,
        account_id: str,
        email: str,
        client_ip: str,
    ) -> None:
        payload = {
            "account_id": account_id,
            "email_hash": _hmac_email(email),
            "client_ip": client_ip,
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=_SYSTEM_FACILITATOR,
            action="account_create",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_verification_code_audit(
        self,
        *,
        account_id: str,
        code: AccountCode,
    ) -> None:
        payload = {
            "account_id": account_id,
            "code_hash": code.hash,
            "ttl_seconds": int((code.expires_at - datetime.now(UTC)).total_seconds()),
            "expires_at": code.expires_at.isoformat(),
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=_SYSTEM_FACILITATOR,
            action="account_verification_emitted",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_verification_consumed_audit(
        self,
        *,
        account_id: str,
        emit_row_id: str,
    ) -> None:
        payload = {
            "account_id": account_id,
            "emit_row_id": emit_row_id,
            "consumed_at": datetime.now(UTC).isoformat(),
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_verification_consumed",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_account_login_audit(
        self,
        *,
        account_id: str,
        client_ip: str,
        rehash_performed: bool,
    ) -> None:
        payload = {
            "account_id": account_id,
            "client_ip": client_ip,
            "rehash_performed": rehash_performed,
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_login",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_password_change_audit(
        self,
        *,
        account_id: str,
        other_sessions_invalidated: int,
    ) -> None:
        payload = {
            "account_id": account_id,
            "other_sessions_invalidated": other_sessions_invalidated,
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_password_change",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_email_change_code_audit(
        self,
        *,
        account_id: str,
        code: AccountCode,
        new_email: str,
    ) -> None:
        payload = {
            "account_id": account_id,
            "code_hash": code.hash,
            "new_email": new_email,
            "expires_at": code.expires_at.isoformat(),
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_email_change_emitted",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_email_change_old_notified_audit(
        self,
        *,
        account_id: str,
        old_email: str,
    ) -> None:
        payload = {"account_id": account_id, "old_email_hash": _hmac_email(old_email)}
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_email_change_old_notified",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_email_change_consumed_audit(
        self,
        *,
        account_id: str,
        emit_row_id: str,
    ) -> None:
        payload = {
            "account_id": account_id,
            "emit_row_id": emit_row_id,
            "consumed_at": datetime.now(UTC).isoformat(),
        }
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_email_change_consumed",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_account_delete_audit(
        self,
        *,
        account_id: str,
        export_sent: bool,
    ) -> None:
        payload = {"account_id": account_id, "export_email_sent": export_sent}
        await self._log_repo.log_admin_action(
            session_id=self._audit_session_id(account_id),
            facilitator_id=account_id,
            action="account_delete",
            target_id=account_id,
            new_value=json.dumps(payload),
        )

    async def _emit_login_failed_audit(
        self,
        *,
        email: str,
        client_ip: str,
        failure_reason: str,
        elapsed_ms: int,
    ) -> None:
        # No account_id is known on login failure (email may be a
        # non-registered address). We still want a row for forensic
        # rate-limit / credential-stuffing analysis. The synthetic
        # session_id uses the email-hash prefix so operators can
        # correlate failed attempts on the same email without storing
        # the plaintext.
        email_hash = _hmac_email(email)
        payload = {
            "client_ip": client_ip,
            "email_hash": email_hash,
            "failure_reason": failure_reason,
            "elapsed_ms": elapsed_ms,
        }
        await self._log_repo.log_admin_action(
            session_id=f"_account_failed_{email_hash[:16]}",
            facilitator_id=_SYSTEM_FACILITATOR,
            action="account_login_failed",
            target_id=email_hash,
            new_value=json.dumps(payload),
        )

    # ------------------------------------------------------------------
    # Internal lookup helper
    # ------------------------------------------------------------------

    async def _lookup_unconsumed_emit_row(
        self,
        *,
        account_id: str,
        code_hash: str,
    ) -> dict | None:
        """Find an unconsumed ``account_verification_emitted`` row.

        Pulls all unconsumed emit rows for this account; filters
        client-side on code_hash and TTL. The N is small (one
        account, one emit per request) so a JSON-aware index on the
        new_value column isn't worth the schema cost.
        """
        rows = await self._account_repo._fetch_all(  # noqa: SLF001 — owned helper
            _LOOKUP_EMIT_SQL,
            self._audit_session_id(account_id),
            account_id,
        )
        return self._first_matching_emit_row(rows=rows, code_hash=code_hash)

    @staticmethod
    def _first_matching_emit_row(
        *,
        rows: list,
        code_hash: str,
    ) -> dict | None:
        """Filter rows by code_hash + non-expired TTL."""
        now = datetime.now(UTC)
        for row in rows:
            try:
                payload = json.loads(row["new_value"]) if row["new_value"] else {}
            except (TypeError, ValueError):
                continue
            if payload.get("code_hash") != code_hash:
                continue
            expires_iso = payload.get("expires_at")
            if expires_iso is None:
                continue
            try:
                expires_at = datetime.fromisoformat(expires_iso)
            except ValueError:
                continue
            if expires_at < now:
                continue
            return {
                "id": row["id"],
                "target_id": row["target_id"],
                "new_value": row["new_value"],
            }
        return None

    # ------------------------------------------------------------------
    # Email transport call wrapper
    # ------------------------------------------------------------------

    async def _send_verification_email(
        self,
        *,
        account_id: str,
        to_email: str,
        code: AccountCode,
    ) -> bool:
        """Hand the plaintext code to the email transport.

        Failure of the transport is logged but does NOT roll back the
        account creation — the operator recovers via the audit log
        per the spec edge case. Returns True iff the transport
        accepted the call without raising.
        """
        body = f"Your verification code: {code.plaintext}\n" "This code expires in 24 hours."
        try:
            await self._email_transport.send(
                to=to_email,
                subject="Verify your SACP account",
                body=body,
                purpose="verification",
            )
            return True
        except Exception:  # noqa: BLE001 — transport failure is operator-recoverable
            log.warning(
                "email transport failed for account %s verification; "
                "operator can retrieve code from admin_audit_log",
                account_id,
                exc_info=True,
            )
            return False


_LOOKUP_EMAIL_CHANGE_SQL = """
    SELECT id, target_id, new_value, timestamp
    FROM admin_audit_log
    WHERE session_id = $1
      AND action = 'account_email_change_emitted'
      AND target_id = $2
      AND NOT EXISTS (
        SELECT 1 FROM admin_audit_log AS consumed
        WHERE consumed.session_id = $1
          AND consumed.action = 'account_email_change_consumed'
          AND consumed.new_value LIKE '%' || admin_audit_log.id::text || '%'
      )
    ORDER BY timestamp DESC
"""

# SQL constant — joined on the synthetic per-account audit session_id so
# we don't scan the entire audit table per request. The "unconsumed"
# check uses NOT EXISTS against ``account_verification_consumed`` rows
# referencing this emit row's id in their payload.
_LOOKUP_EMIT_SQL = """
    SELECT id, target_id, new_value, timestamp
    FROM admin_audit_log
    WHERE session_id = $1
      AND action = 'account_verification_emitted'
      AND target_id = $2
      AND NOT EXISTS (
        SELECT 1 FROM admin_audit_log AS consumed
        WHERE consumed.session_id = $1
          AND consumed.action = 'account_verification_consumed'
          AND consumed.new_value LIKE '%' || admin_audit_log.id::text || '%'
      )
    ORDER BY timestamp DESC
"""
