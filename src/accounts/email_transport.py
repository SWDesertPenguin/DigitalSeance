# SPDX-License-Identifier: AGPL-3.0-or-later

"""Email-transport ABC + noop adapter for spec 023.

Defines the :class:`EmailTransport` ``Protocol`` and the v1 default
:class:`NoopEmailTransport` adapter, plus the
:func:`select_transport` factory that reads ``SACP_EMAIL_TRANSPORT``
at startup and raises :class:`EmailTransportNotImplemented` for the
reserved ``smtp`` / ``ses`` / ``sendgrid`` values until the
follow-up email-transport spec lands.

The noop adapter records each call as an ``admin_audit_log`` row
shaped per ``contracts/email-transport.md`` (purpose, ``to_hashed``,
``subject``, ``body_length``). Body content is NEVER included in the
audit row; only the length appears for forensic sanity-checking.
Plaintext access in dev/staging deployments routes through the
``account_*_emitted`` audit row's ``_dev_plaintext`` field, written
separately by the service-layer code that calls the transport.

See ``specs/023-user-accounts/contracts/email-transport.md`` for the
full contract and ``specs/023-user-accounts/research.md`` §4 + §6 for
the design notes.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

EmailPurpose = Literal[
    "verification",
    "password_reset",
    "email_change_new",
    "email_change_old_notify",
    "account_delete_export",
]

# Audit-row writer. The transport stays decoupled from asyncpg; the
# orchestrator wires the real DB writer in at startup. Tests use a
# simple capture-list to inspect the rows without a Postgres dep.
AuditRowWriter = Callable[[dict[str, object]], Awaitable[None]]

log = logging.getLogger(__name__)


class EmailTransportUnavailable(RuntimeError):  # noqa: N818 — error suffix avoided to match contract
    """Raised when a real transport cannot deliver. Caller falls back to audit-log only.

    Name is documented as ``EmailTransportUnavailable`` in
    ``contracts/email-transport.md``; the public name is part of the
    locked v1 contract so the follow-up spec's real adapters re-use
    the same exception class without a rename.
    """


class EmailTransportNotImplemented(RuntimeError):  # noqa: N818 — name documented in contract
    """SACP_EMAIL_TRANSPORT={smtp,ses,sendgrid} is reserved for follow-up spec.

    v1 supports only 'noop'. See
    ``specs/023-user-accounts/contracts/email-transport.md`` for the
    follow-up scope.
    """


class EmailTransport(Protocol):
    """Process-scope adapter for outbound email.

    Selected at startup via ``SACP_EMAIL_TRANSPORT`` (one of: noop,
    smtp, ses, sendgrid). v1 ships only the noop adapter; smtp / ses /
    sendgrid raise :class:`EmailTransportNotImplemented` at startup.

    Spec 023 FR-022. Research.md §4, §6.
    """

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        purpose: EmailPurpose,
    ) -> None:
        """Emit one outbound email.

        Implementations MUST be idempotent on caller-controlled retry
        (the caller retries on transient failure; the transport MUST
        NOT enqueue duplicate sends). Implementations MUST NOT log
        ``body`` content; only ``purpose``, hashed ``to``, and
        ``len(body)`` may appear in audit-log payloads.

        Raises:
            EmailTransportUnavailable: when the transport cannot
                deliver. Caller falls back to admin_audit_log-only
                recording per the spec 023 edge case.
        """
        ...


def _hash_to(to_address: str) -> str:
    """HMAC-SHA256 of the recipient under SACP_AUTH_LOOKUP_KEY.

    Mirrors :func:`src.accounts.codes.hash_code` so the audit-log
    payload's ``to_hashed`` field stays consistent with the rest of
    the spec 023 hashed-PII scheme. Lower-cases the input first to
    match the application-side email canonicalization (research §2).
    """
    key = os.environ.get("SACP_AUTH_LOOKUP_KEY", "")
    if not key:
        raise RuntimeError(
            "SACP_AUTH_LOOKUP_KEY is required to hash recipient addresses; "
            "the V16 validator should have rejected an empty value at startup."
        )
    digest = hmac.new(
        key.encode("utf-8"),
        to_address.lower().encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()


class NoopEmailTransport:
    """V1 default adapter — writes a structured audit-log row, no network call.

    Constructed with an optional ``audit_writer`` callable; when
    omitted, the adapter logs the row at WARNING level instead so
    test harnesses that don't wire a DB still observe the call.
    Production wiring passes the real writer at startup.
    """

    def __init__(self, *, audit_writer: AuditRowWriter | None = None) -> None:
        self._audit_writer = audit_writer

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        purpose: EmailPurpose,
    ) -> None:
        """Write the audit-log row described in ``contracts/email-transport.md``."""
        row = {
            "action": "account_email_noop_emitted",
            "purpose": purpose,
            "to_hashed": _hash_to(to),
            "subject": subject,
            "body_length": len(body),
        }
        if self._audit_writer is not None:
            await self._audit_writer(row)
        else:
            log.warning(
                "NoopEmailTransport.send invoked without audit_writer; " "row=%s",
                row,
            )


def select_transport(
    *,
    audit_writer: AuditRowWriter | None = None,
) -> EmailTransport:
    """Read SACP_EMAIL_TRANSPORT and return the configured adapter.

    Returns :class:`NoopEmailTransport` for ``noop``. Raises
    :class:`EmailTransportNotImplemented` for ``smtp`` / ``ses`` /
    ``sendgrid`` — these enum values are reserved for the follow-up
    transport spec; the V16 validator accepts them syntactically so
    operators see a clear ERROR at startup rather than a silent
    fallback to noop. Raises :class:`ValueError` for any other value
    (the validator already rejects out-of-set values, so this branch
    is the belt-and-braces guard against a validator bypass).
    """
    name = os.environ.get("SACP_EMAIL_TRANSPORT", "noop")
    if name == "noop":
        return NoopEmailTransport(audit_writer=audit_writer)
    if name in ("smtp", "ses", "sendgrid"):
        raise EmailTransportNotImplemented(
            f"SACP_EMAIL_TRANSPORT={name!r} is reserved for a follow-up "
            "spec; v1 supports only 'noop'. See "
            "specs/023-user-accounts/contracts/email-transport.md."
        )
    raise ValueError(f"Unknown SACP_EMAIL_TRANSPORT value: {name!r}")
