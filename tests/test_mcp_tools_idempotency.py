# SPDX-License-Identifier: AGPL-3.0-or-later
"""T100: idempotency helpers. Spec 030 Phase 3."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_check_idempotency_returns_none_without_pool() -> None:
    """check_idempotency returns None gracefully when pool is None."""
    from src.mcp_protocol.idempotency import check_idempotency

    result = await check_idempotency(None, "key-1", "session.get", "sid", "pid")
    assert result is None


@pytest.mark.asyncio
async def test_record_idempotency_noop_without_pool() -> None:
    """record_idempotency completes without raising when pool is None."""
    from src.mcp_protocol.idempotency import record_idempotency

    await record_idempotency(
        None, "key-1", "session.get", session_id="sid", participant_id="pid", result={"ok": True}
    )


def test_idempotency_module_imports_cleanly() -> None:
    """Idempotency module imports without side effects."""
    import src.mcp_protocol.idempotency as mod

    assert hasattr(mod, "check_idempotency")
    assert hasattr(mod, "record_idempotency")
