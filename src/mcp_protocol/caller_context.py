# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-dispatch caller context. Spec 030 Phase 2, tool-registry-shape.md."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CallerContext:
    """Per-dispatch context passed to every tool dispatch callable."""

    participant_id: str
    session_id: str | None
    scopes: frozenset[str]
    is_ai_caller: bool
    mcp_session_id: str | None
    request_id: str
    dispatch_started_at: datetime
    idempotency_key: str | None
    db_pool: Any | None = None
    encryption_key: str | None = None
