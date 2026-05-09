# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 mount-gate + cross-validator WARN tests (T034, T036).

T034: ``should_mount_account_router`` honors both
``SACP_ACCOUNTS_ENABLED`` (FR-018) and ``SACP_TOPOLOGY`` (research
§12). Topology 7 emits a startup ERROR and refuses to mount; off-state
silently returns False.

T036: ``emit_accounts_email_transport_warning`` emits a structured
WARN log when ``SACP_ACCOUNTS_ENABLED=1`` AND
``SACP_EMAIL_TRANSPORT=noop`` simultaneously (research §13). The
function MUST NOT raise — production safety lives in the WARN log,
not in a fail-closed validator.
"""

from __future__ import annotations

import logging

import pytest

from src.accounts import (
    emit_accounts_email_transport_warning,
    should_mount_account_router,
)

# ---------------------------------------------------------------------------
# Mount gate (T034)
# ---------------------------------------------------------------------------


def test_mount_gate_off_when_master_switch_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-018: unset master switch keeps the router unmounted."""
    monkeypatch.delenv("SACP_ACCOUNTS_ENABLED", raising=False)
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    assert should_mount_account_router() is False


def test_mount_gate_off_when_master_switch_explicit_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-018: explicit '0' keeps the router unmounted."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "0")
    monkeypatch.delenv("SACP_TOPOLOGY", raising=False)
    assert should_mount_account_router() is False


def test_mount_gate_on_when_master_switch_one_and_safe_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-018: '1' + topology 1-6 mounts the router."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.setenv("SACP_TOPOLOGY", "1")
    assert should_mount_account_router() is True


@pytest.mark.parametrize("topology", ["1", "2", "3", "4", "5", "6"])
def test_mount_gate_on_for_supported_topologies(
    monkeypatch: pytest.MonkeyPatch,
    topology: str,
) -> None:
    """Spec V12: topologies 1-6 are supported."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.setenv("SACP_TOPOLOGY", topology)
    assert should_mount_account_router() is True


def test_mount_gate_blocks_topology_7_with_error_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Research §12: topology 7 refuses to mount and emits a startup ERROR."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    caplog.set_level(logging.ERROR, logger="src.accounts")
    assert should_mount_account_router() is False
    matching = [r for r in caplog.records if "SACP_TOPOLOGY=7" in r.getMessage()]
    assert matching, (
        "expected startup ERROR naming SACP_TOPOLOGY=7 incompatibility; got: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def test_mount_gate_off_takes_precedence_over_topology_7(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Master-switch-off short-circuits the topology check (no ERROR emitted)."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "0")
    monkeypatch.setenv("SACP_TOPOLOGY", "7")
    caplog.set_level(logging.ERROR, logger="src.accounts")
    assert should_mount_account_router() is False
    # Off-state silence — topology ERROR shouldn't fire when accounts are off.
    matching = [r for r in caplog.records if "SACP_TOPOLOGY=7" in r.getMessage()]
    assert not matching, (
        f"unexpected topology ERROR with master switch off: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Cross-validator WARN (T036)
# ---------------------------------------------------------------------------


def test_warn_emitted_when_accounts_on_and_transport_noop(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Research §13: accounts=1 + transport=noop emits a startup WARN."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "noop")
    caplog.set_level(logging.WARNING, logger="src.accounts")
    emit_accounts_email_transport_warning()
    matching = [r for r in caplog.records if "Not suitable for production" in r.getMessage()]
    assert matching, (
        "expected production-unsafe WARN; got: " f"{[r.getMessage() for r in caplog.records]}"
    )


def test_warn_silent_when_accounts_off(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No WARN when accounts are off; transport choice is moot."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "0")
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "noop")
    caplog.set_level(logging.WARNING, logger="src.accounts")
    emit_accounts_email_transport_warning()
    matching = [r for r in caplog.records if "Not suitable for production" in r.getMessage()]
    assert not matching


def test_warn_silent_when_transport_is_real_value(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No WARN when transport is something other than noop.

    The reserved smtp/ses/sendgrid values fail at adapter
    instantiation rather than at this WARN — different signal path.
    """
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "smtp")
    caplog.set_level(logging.WARNING, logger="src.accounts")
    emit_accounts_email_transport_warning()
    matching = [r for r in caplog.records if "Not suitable for production" in r.getMessage()]
    assert not matching


def test_warn_does_not_raise_on_problematic_combo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The WARN function MUST NOT raise — V16 fail-closed stays clean."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "1")
    monkeypatch.setenv("SACP_EMAIL_TRANSPORT", "noop")
    # Returns None, does not raise.
    assert emit_accounts_email_transport_warning() is None
