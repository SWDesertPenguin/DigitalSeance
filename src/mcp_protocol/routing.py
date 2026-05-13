# SPDX-License-Identifier: AGPL-3.0-or-later
"""Spec 022 cross-instance dispatch stub. Spec 030 Phase 2, FR-004 (research.md §4)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger("sacp.mcp.routing")


async def route_or_passthrough(
    session_id: str | None,
    dispatch_fn: Callable[[], Awaitable[Any]],
) -> Any:
    """Check binding registry for cross-instance routing; fall through locally.

    Phase 2: the spec 022 binding registry may not be deployed. This function
    always calls dispatch_fn locally. Phase 3 amends this to consult the
    registry and proxy the request cross-instance when the bound instance
    differs from the current one.
    """
    if session_id is not None:
        _maybe_log_cross_instance(session_id)
    return await dispatch_fn()


def _maybe_log_cross_instance(session_id: str) -> None:
    """No-op in Phase 2; Phase 3 replaces with actual registry lookup."""
