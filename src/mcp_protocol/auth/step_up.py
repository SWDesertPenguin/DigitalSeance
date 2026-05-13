# SPDX-License-Identifier: AGPL-3.0-or-later
"""Step-up authentication freshness check for destructive tools. Spec 030 Phase 4 FR-086."""

from __future__ import annotations

import os
from datetime import UTC, datetime

DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "admin.transfer_facilitator",
        "admin.archive_session",
        "admin.mass_revoke_tokens",
        "session.delete",
    }
)


def _freshness_seconds() -> int:
    val = os.environ.get("SACP_OAUTH_STEP_UP_FRESHNESS_SECONDS", "300")
    try:
        return max(30, min(3600, int(val)))
    except (ValueError, TypeError):
        return 300


def requires_step_up(
    tool_name: str,
    auth_time: datetime,
    freshness_seconds: int | None = None,
) -> bool:
    """Return True if step-up is needed for this tool + auth_time combination."""
    if tool_name not in DESTRUCTIVE_TOOLS:
        return False
    limit = freshness_seconds if freshness_seconds is not None else _freshness_seconds()
    now = datetime.now(tz=UTC)
    if auth_time.tzinfo is None:
        auth_time = auth_time.replace(tzinfo=UTC)
    age = (now - auth_time).total_seconds()
    return age > limit
