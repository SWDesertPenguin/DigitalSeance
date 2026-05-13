# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for step-up authentication freshness check. Spec 030 Phase 4 FR-086."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.mcp_protocol.auth.step_up import DESTRUCTIVE_TOOLS, requires_step_up


def test_fresh_token_no_step_up() -> None:
    auth_time = datetime.now(tz=UTC) - timedelta(seconds=10)
    assert requires_step_up("admin.transfer_facilitator", auth_time, freshness_seconds=300) is False


def test_stale_token_destructive_tool_requires_step_up() -> None:
    auth_time = datetime.now(tz=UTC) - timedelta(seconds=400)
    assert requires_step_up("admin.archive_session", auth_time, freshness_seconds=300) is True


def test_non_destructive_tool_never_requires_step_up() -> None:
    auth_time = datetime.now(tz=UTC) - timedelta(days=365)
    assert requires_step_up("session.list", auth_time, freshness_seconds=1) is False


def test_all_destructive_tools_listed() -> None:
    expected = {
        "admin.transfer_facilitator",
        "admin.archive_session",
        "admin.mass_revoke_tokens",
        "session.delete",
    }
    assert expected.issubset(DESTRUCTIVE_TOOLS)
