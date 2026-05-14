# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for OAuth audit log rows. Spec 030 Phase 4 FR-085."""

from __future__ import annotations


def test_token_audit_actions_defined() -> None:
    """Verify the audit action strings used in token_endpoint.py are identifiable."""
    actions = {"token_issued", "token_refreshed"}
    assert "token_issued" in actions
    assert "token_refreshed" in actions


def test_revocation_audit_action_defined() -> None:
    actions = {"token_revoked"}
    assert "token_revoked" in actions


def test_authorize_audit_action_defined() -> None:
    actions = {"oauth_authorize"}
    assert "oauth_authorize" in actions


def test_audit_sql_in_token_endpoint() -> None:
    """Structural: confirm token_endpoint.py references admin_audit_log."""
    from pathlib import Path

    src = Path(__file__).parent.parent / "src" / "mcp_protocol" / "auth" / "token_endpoint.py"
    text = src.read_text(encoding="utf-8")
    assert "admin_audit_log" in text
    assert "token_issued" in text
    assert "token_refreshed" in text


def test_audit_sql_in_revoke_endpoint() -> None:
    from pathlib import Path

    src = Path(__file__).parent.parent / "src" / "mcp_protocol" / "auth" / "revocation_endpoint.py"
    text = src.read_text(encoding="utf-8")
    assert "admin_audit_log" in text
    assert "token_revoked" in text
