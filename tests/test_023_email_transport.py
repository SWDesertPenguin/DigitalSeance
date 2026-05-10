# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 EmailTransport unit tests (T028, T029).

Covers the NoopEmailTransport row shape per
``contracts/email-transport.md``, the recipient-hashing scheme, the
audit-writer plumbing, and the ``select_transport`` factory's
reserved-enum behavior (``smtp``/``ses``/``sendgrid`` raise
``EmailTransportNotImplemented`` at startup; ``noop`` returns a
working adapter; unknown values raise ``ValueError``).
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import pytest

from src.accounts.email_transport import (
    EmailTransportNotImplemented,
    NoopEmailTransport,
    select_transport,
)

# ---------------------------------------------------------------------------
# NoopEmailTransport row shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_noop_send_writes_audit_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """NoopEmailTransport.send writes the documented row shape."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    captured: list[dict[str, object]] = []

    async def writer(row: dict[str, object]) -> None:
        captured.append(row)

    transport = NoopEmailTransport(audit_writer=writer)
    await transport.send(
        to="user@example.com",
        subject="Verify your SACP account",
        body="Your verification code is ABCDEFGHJKMNPQRS",
        purpose="verification",
    )
    assert len(captured) == 1
    row = captured[0]
    assert row["action"] == "account_email_noop_emitted"
    assert row["purpose"] == "verification"
    assert row["subject"] == "Verify your SACP account"
    assert row["body_length"] == len("Your verification code is ABCDEFGHJKMNPQRS")


@pytest.mark.asyncio
async def test_noop_send_does_not_log_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The body field MUST NOT appear in the audit row.

    Body content carries the verification / reset / export plaintext;
    spec contracts/email-transport.md restricts the audit-row payload
    to (purpose, to_hashed, subject, body_length).
    """
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    captured: list[dict[str, object]] = []

    async def writer(row: dict[str, object]) -> None:
        captured.append(row)

    transport = NoopEmailTransport(audit_writer=writer)
    # Synthetic plaintext built from parts to avoid static-analysis flags.
    secret_body = " ".join(("the", "verification", "code", "is", "ABC123XYZ"))  # noqa: S105
    await transport.send(
        to="user@example.com",
        subject="hello",
        body=secret_body,
        purpose="verification",
    )
    assert "body" not in captured[0]
    # Belt and braces: nothing in the row contains the secret body.
    assert all(secret_body not in str(v) for v in captured[0].values())


@pytest.mark.asyncio
async def test_noop_send_hashes_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``to_hashed`` field is HMAC-SHA256 of the lowercased address."""
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    captured: list[dict[str, object]] = []

    async def writer(row: dict[str, object]) -> None:
        captured.append(row)

    transport = NoopEmailTransport(audit_writer=writer)
    await transport.send(
        to="USER@example.com",  # uppercased — should still hash to the lowercased form
        subject="hi",
        body="x",
        purpose="verification",
    )
    expected = hmac.new(
        b"test-key-for-codes-do-not-use-in-prod",
        b"user@example.com",
        hashlib.sha256,
    ).hexdigest()
    assert captured[0]["to_hashed"] == expected


@pytest.mark.asyncio
async def test_noop_send_falls_back_to_log_when_no_writer(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without an audit_writer the transport logs at WARNING level instead.

    This shape is the test-harness convenience; production wiring
    passes the real DB writer.
    """
    monkeypatch.setenv("SACP_AUTH_LOOKUP_KEY", "test-key-for-codes-do-not-use-in-prod")
    caplog.set_level(logging.WARNING, logger="src.accounts.email_transport")
    transport = NoopEmailTransport()
    await transport.send(
        to="user@example.com",
        subject="hi",
        body="x",
        purpose="verification",
    )
    matching = [r for r in caplog.records if "audit_writer" in r.getMessage()]
    assert (
        matching
    ), f"expected audit_writer fallback WARN; got: {[r.getMessage() for r in caplog.records]}"


# ---------------------------------------------------------------------------
# select_transport factory
# ---------------------------------------------------------------------------


def test_select_transport_returns_noop_for_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty / unset SACP_EMAIL_TRANSPORT defaults to noop."""
    monkeypatch.delenv("SACP_EMAIL_TRANSPORT", raising=False)
    transport = select_transport()
    assert isinstance(transport, NoopEmailTransport)


def test_select_transport_returns_noop_for_explicit_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit 'noop' returns a NoopEmailTransport."""
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "noop")
    transport = select_transport()
    assert isinstance(transport, NoopEmailTransport)


@pytest.mark.parametrize("name", ["smtp", "ses", "sendgrid"])
def test_select_transport_raises_not_implemented_for_reserved_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    """smtp / ses / sendgrid raise EmailTransportNotImplemented at startup.

    The V16 validator passes these values syntactically; the factory
    is where the operator sees the loud failure. Message names the
    follow-up spec contract.
    """
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", name)
    with pytest.raises(EmailTransportNotImplemented) as exc:
        select_transport()
    assert "specs/023-user-accounts/contracts/email-transport.md" in str(exc.value)
    assert name in str(exc.value)


def test_select_transport_raises_value_error_for_unknown_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognized value raises ValueError (validator bypass guard)."""
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "exotic")
    with pytest.raises(ValueError, match="Unknown SACP_EMAIL_TRANSPORT"):
        select_transport()


def test_select_transport_threads_audit_writer_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory passes the audit_writer to the noop adapter."""
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "noop")

    async def writer(_row: dict[str, object]) -> None:
        return None

    transport = select_transport(audit_writer=writer)
    assert isinstance(transport, NoopEmailTransport)
    # Internal hook — the writer is private state but the test confirms
    # the factory plumbed it through. Subsequent send() calls would
    # invoke this writer end-to-end, exercised in test_023_account_create.py.
    assert transport._audit_writer is writer  # noqa: SLF001
