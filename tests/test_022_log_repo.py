# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 log_repo unit tests (T026 + T036 of tasks.md).

Covers ``LogRepository.get_detection_events_page`` and
``LogRepository.get_disposition_timeline`` at the unit level — SQL
shape, parameter binding, and row projection. Schema-level integration
tests (alembic 017 round-trip, CHECK constraint enforcement) live in
the existing ``tests/test_alembic_*.py`` family and run against
``@pytest.mark.requires_postgres``.

The repository methods are thin wrappers around ``pool.fetch`` /
``pool.acquire().fetch`` so the unit surface here is:

- SQL string contains the documented WHERE/ORDER/LIMIT clauses.
- ``max_events=None`` produces SQL without a LIMIT.
- ``since=None`` is passed through as the second parameter.
- Returned rows are coerced from asyncpg.Record-ish into plain dicts.
- Disposition timeline filters on the registered action set and orders
  ascending.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.log_repo import LogRepository


def _fake_pool(fetch_return_value):
    """Build a fake asyncpg pool whose acquired conn.fetch returns the value."""
    conn = SimpleNamespace(
        fetch=AsyncMock(return_value=fetch_return_value),
    )

    class _AcquireCtx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *_args):
            return False

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCtx())
    return pool, conn


# ---------------------------------------------------------------------------
# get_detection_events_page — SQL shape + parameter binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_detection_events_page_emits_no_limit_when_max_none() -> None:
    """``max_events=None`` ⇒ SQL has no LIMIT clause and 2 params bound."""
    pool, conn = _fake_pool([])
    repo = LogRepository(pool)
    await repo.get_detection_events_page("s1", max_events=None, since=None)
    sql_text, *params = conn.fetch.await_args.args
    assert "LIMIT" not in sql_text
    assert "WHERE session_id = $1" in sql_text
    assert "ORDER BY timestamp DESC" in sql_text
    assert params == ["s1", None]


@pytest.mark.asyncio
async def test_get_detection_events_page_emits_limit_when_max_set() -> None:
    """``max_events=50`` ⇒ SQL has LIMIT $3 and 3 params bound."""
    pool, conn = _fake_pool([])
    repo = LogRepository(pool)
    await repo.get_detection_events_page("s1", max_events=50, since=None)
    sql_text, *params = conn.fetch.await_args.args
    assert "LIMIT $3" in sql_text
    assert params == ["s1", None, 50]


@pytest.mark.asyncio
async def test_get_detection_events_page_passes_since_through() -> None:
    """``since`` is bound as parameter 2 (the retention lower bound)."""
    cutoff = datetime(2026, 5, 1, tzinfo=UTC)
    pool, conn = _fake_pool([])
    repo = LogRepository(pool)
    await repo.get_detection_events_page("s1", max_events=None, since=cutoff)
    _, *params = conn.fetch.await_args.args
    assert params == ["s1", cutoff]


@pytest.mark.asyncio
async def test_get_detection_events_page_coerces_rows_to_dict() -> None:
    """Repository returns plain dicts (callers shouldn't see asyncpg.Record)."""
    fake_row = {
        "id": 1,
        "session_id": "s1",
        "event_class": "ai_question_opened",
        "participant_id": "p1",
        "trigger_snippet": "what?",
        "detector_score": 0.5,
        "turn_number": 3,
        "timestamp": datetime(2026, 5, 11, tzinfo=UTC),
        "disposition": "pending",
        "last_disposition_change_at": None,
    }
    pool, _conn = _fake_pool([fake_row])
    repo = LogRepository(pool)
    rows = await repo.get_detection_events_page("s1", max_events=None, since=None)
    assert rows == [fake_row]
    assert isinstance(rows[0], dict)


# ---------------------------------------------------------------------------
# get_disposition_timeline — SQL shape + parameter binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disposition_timeline_filters_on_action_set() -> None:
    """The timeline query SHOULD include all four detection_event_* actions."""
    pool, conn = _fake_pool([])
    repo = LogRepository(pool)
    await repo.get_disposition_timeline("s1", 99)
    sql_text, *params = conn.fetch.await_args.args
    assert "detection_event_acknowledged" in sql_text
    assert "detection_event_dismissed" in sql_text
    assert "detection_event_auto_resolved" in sql_text
    assert "detection_event_resurface" in sql_text


@pytest.mark.asyncio
async def test_disposition_timeline_binds_event_id_as_text() -> None:
    """``target_id`` is TEXT in admin_audit_log — bind the event id stringified."""
    pool, conn = _fake_pool([])
    repo = LogRepository(pool)
    await repo.get_disposition_timeline("s1", 99)
    _, *params = conn.fetch.await_args.args
    assert params == ["s1", "99"]


@pytest.mark.asyncio
async def test_disposition_timeline_orders_ascending() -> None:
    """Timeline is rendered oldest-first (click-expand view)."""
    pool, conn = _fake_pool([])
    repo = LogRepository(pool)
    await repo.get_disposition_timeline("s1", 99)
    sql_text, *_ = conn.fetch.await_args.args
    assert "ORDER BY timestamp ASC" in sql_text


@pytest.mark.asyncio
async def test_disposition_timeline_returns_plain_dicts() -> None:
    """Timeline rows surface as dicts for the endpoint serializer."""
    fake_row = {
        "id": 7,
        "action": "detection_event_dismissed",
        "facilitator_id": "f1",
        "timestamp": datetime(2026, 5, 11, tzinfo=UTC),
    }
    pool, _conn = _fake_pool([fake_row])
    repo = LogRepository(pool)
    rows = await repo.get_disposition_timeline("s1", 7)
    assert rows == [fake_row]
