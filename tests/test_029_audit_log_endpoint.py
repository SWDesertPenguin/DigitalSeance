# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 audit-log endpoint integration coverage (T016 / T018 / T019).

Drives ``LogRepository.get_audit_log_page`` against a real Postgres
test database (the ``pool`` fixture in conftest.py), validating the
behaviors documented in
``specs/029-audit-log-viewer/contracts/audit-log-endpoint.md``:

- T016 surface (reverse-chrono ordering, pagination metadata,
  retention cap) — auth/limit/parameter-range tests already live in
  ``tests/test_029_admin_endpoint_helpers.py`` with monkeypatched env;
  this file covers the parts that need real rows on disk.
- T018 scrub passthrough — ``rotate_token`` row at the FR-001 endpoint
  returns ``[scrubbed]`` for both value columns; spec 010 debug-export
  still sees the raw values (forensic-walkability invariant).
- T019 unregistered-action fallback — the registered ``[unregistered:
  <raw>]`` label appears for novel action strings, AND a WARN log is
  emitted by the registry helper.

Skips cleanly if Postgres is unreachable (the ``pool`` fixture itself
issues the ``pytest.skip`` per CLAUDE.md ``feedback_test_schema_mirror``).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from src.orchestrator.audit_log_view import SCRUBBED_PLACEHOLDER
from src.repositories.log_repo import LogRepository

# Mark every coroutine in this file as an asyncio test.
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — minimal session/participant fixture insertion
# ---------------------------------------------------------------------------


async def _insert_session(pool: asyncpg.Pool) -> tuple[str, str]:
    """Insert a session + facilitator participant; return (session_id, facilitator_id)."""

    session_id = str(uuid.uuid4())
    facilitator_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES ($1, $2, 'active')",
            session_id,
            "spec-029 endpoint test",
        )
        await conn.execute(
            """
            INSERT INTO participants
                (id, session_id, display_name, role, status,
                 provider, model, model_tier, model_family, context_window)
            VALUES ($1, $2, 'Alice', 'facilitator', 'active',
                    'openai', 'gpt-4o', 'high', 'gpt', 128000)
            """,
            facilitator_id,
            session_id,
        )
        await conn.execute(
            "UPDATE sessions SET facilitator_id = $1 WHERE id = $2",
            facilitator_id,
            session_id,
        )
    return session_id, facilitator_id


async def _insert_audit_row_at(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    facilitator_id: str,
    action: str,
    target_id: str,
    timestamp: datetime,
    previous_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Insert an admin_audit_log row with a fixed timestamp.

    Bypasses ``log_admin_action`` so the test can backdate rows for
    retention-cap and ordering coverage.
    """

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO admin_audit_log
                (session_id, facilitator_id, action, target_id,
                 previous_value, new_value, timestamp)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            session_id,
            facilitator_id,
            action,
            target_id,
            previous_value,
            new_value,
            timestamp,
        )


# ---------------------------------------------------------------------------
# T016 — endpoint surface (ordering / pagination / retention)
# ---------------------------------------------------------------------------


async def test_audit_log_page_reverse_chronological_order(pool: asyncpg.Pool) -> None:
    """Rows ship newest-first (FR-005 + research.md §6 ORDER BY timestamp DESC)."""

    session_id, facilitator_id = await _insert_session(pool)
    base = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    actions = [
        ("add_participant", base + timedelta(seconds=1)),
        ("approve_participant", base + timedelta(seconds=2)),
        ("remove_participant", base + timedelta(seconds=3)),
    ]
    for action, ts in actions:
        await _insert_audit_row_at(
            pool,
            session_id=session_id,
            facilitator_id=facilitator_id,
            action=action,
            target_id=facilitator_id,
            timestamp=ts,
        )

    page = await LogRepository(pool).get_audit_log_page(session_id, offset=0, limit=10)
    assert page.total_count == 3
    actions_in_order = [r.action for r in page.rows]
    assert actions_in_order == [
        "remove_participant",
        "approve_participant",
        "add_participant",
    ]


async def test_audit_log_page_pagination_metadata(pool: asyncpg.Pool) -> None:
    """next_offset advances correctly; goes None on the last page."""

    session_id, facilitator_id = await _insert_session(pool)
    base = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    for i in range(5):
        await _insert_audit_row_at(
            pool,
            session_id=session_id,
            facilitator_id=facilitator_id,
            action="add_participant",
            target_id=facilitator_id,
            timestamp=base + timedelta(seconds=i),
        )

    repo = LogRepository(pool)
    first = await repo.get_audit_log_page(session_id, offset=0, limit=2)
    assert first.total_count == 5
    assert first.next_offset == 2
    assert len(first.rows) == 2

    second = await repo.get_audit_log_page(session_id, offset=2, limit=2)
    assert second.next_offset == 4
    assert len(second.rows) == 2

    third = await repo.get_audit_log_page(session_id, offset=4, limit=2)
    assert third.next_offset is None
    assert len(third.rows) == 1


async def _seed_two_rows_at_relative_days(
    pool: asyncpg.Pool, *, days_recent: int, days_old: int
) -> str:
    """Insert two audit rows at the requested relative ages; return session_id."""

    session_id, facilitator_id = await _insert_session(pool)
    now = datetime.now(UTC)
    for action, days_ago in (
        ("add_participant", days_recent),
        ("remove_participant", days_old),
    ):
        await _insert_audit_row_at(
            pool,
            session_id=session_id,
            facilitator_id=facilitator_id,
            action=action,
            target_id=facilitator_id,
            timestamp=now - timedelta(days=days_ago),
        )
    return session_id


async def test_audit_log_page_retention_cap_excludes_old_rows(pool: asyncpg.Pool) -> None:
    """retention_days = N hides rows older than N days (FR-016)."""

    session_id = await _seed_two_rows_at_relative_days(pool, days_recent=2, days_old=10)
    repo = LogRepository(pool)
    full = await repo.get_audit_log_page(session_id, offset=0, limit=10)
    assert full.total_count == 2

    capped = await repo.get_audit_log_page(session_id, offset=0, limit=10, retention_days=5)
    assert capped.total_count == 1
    assert capped.rows[0].action == "add_participant"


async def test_audit_log_page_isolated_by_session(pool: asyncpg.Pool) -> None:
    """Cross-session rows do NOT bleed into another session's page."""

    s1, f1 = await _insert_session(pool)
    s2, f2 = await _insert_session(pool)
    base = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
    await _insert_audit_row_at(
        pool,
        session_id=s1,
        facilitator_id=f1,
        action="add_participant",
        target_id=f1,
        timestamp=base,
    )
    await _insert_audit_row_at(
        pool,
        session_id=s2,
        facilitator_id=f2,
        action="remove_participant",
        target_id=f2,
        timestamp=base,
    )

    page1 = await LogRepository(pool).get_audit_log_page(s1, offset=0, limit=10)
    assert page1.total_count == 1
    assert page1.rows[0].action == "add_participant"


# ---------------------------------------------------------------------------
# T018 — scrub passthrough at FR-001 endpoint + spec 010 invariant
# ---------------------------------------------------------------------------


async def test_rotate_token_row_returns_scrubbed_at_endpoint(pool: asyncpg.Pool) -> None:
    """FR-014: rotate_token's previous_value / new_value MUST render scrubbed."""

    session_id, facilitator_id = await _insert_session(pool)
    raw_old = "old-secret-token-AAAA1111"
    raw_new = "new-secret-token-BBBB2222"
    await _insert_audit_row_at(
        pool,
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="rotate_token",
        target_id=facilitator_id,
        timestamp=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC),
        previous_value=raw_old,
        new_value=raw_new,
    )

    page = await LogRepository(pool).get_audit_log_page(session_id, offset=0, limit=10)
    assert len(page.rows) == 1
    row = page.rows[0]
    assert row.previous_value == SCRUBBED_PLACEHOLDER
    assert row.new_value == SCRUBBED_PLACEHOLDER


async def test_spec010_debug_export_path_returns_raw_values(pool: asyncpg.Pool) -> None:
    """Forensic-walkability invariant: spec 010's get_audit_log returns raw.

    The FR-014 scrub lives in the spec 029 ``decorate_row`` helper, NOT
    in the underlying ``admin_audit_log`` columns. Spec 010 debug-export
    reads via ``LogRepository.get_audit_log`` (no decoration); that path
    MUST still surface the raw values for forensic review.
    """

    session_id, facilitator_id = await _insert_session(pool)
    raw_old = "old-secret-token-CCCC3333"
    raw_new = "new-secret-token-DDDD4444"
    await _insert_audit_row_at(
        pool,
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="rotate_token",
        target_id=facilitator_id,
        timestamp=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC),
        previous_value=raw_old,
        new_value=raw_new,
    )

    raw_rows = await LogRepository(pool).get_audit_log(session_id)
    assert len(raw_rows) == 1
    assert raw_rows[0].previous_value == raw_old
    assert raw_rows[0].new_value == raw_new


# ---------------------------------------------------------------------------
# T019 — unregistered-action fallback + WARN log
# ---------------------------------------------------------------------------


async def test_unregistered_action_renders_fallback_label_and_logs_warning(
    pool: asyncpg.Pool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """FR-015: novel actions render '[unregistered: <raw>]' AND log WARN."""

    session_id, facilitator_id = await _insert_session(pool)
    await _insert_audit_row_at(
        pool,
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="totally_made_up_action_v1",
        target_id=facilitator_id,
        timestamp=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC),
    )

    with caplog.at_level(logging.WARNING, logger="src.orchestrator.audit_labels"):
        page = await LogRepository(pool).get_audit_log_page(session_id, offset=0, limit=10)

    assert page.rows[0].action_label == "[unregistered: totally_made_up_action_v1]"
    drift_records = [
        rec
        for rec in caplog.records
        if "audit_label_drift" in rec.getMessage()
        and "totally_made_up_action_v1" in rec.getMessage()
    ]
    assert drift_records, "FR-015: orchestrator MUST emit a WARN log naming the missing key"


# ---------------------------------------------------------------------------
# T017 — supplemental WS coverage (dedup-on-id + within-2s emission)
#
# The unit-level scrub / role-filter / durability tests live in
# tests/test_029_audit_broadcast.py. These two cases exercise the
# end-to-end durability + timing contract from
# contracts/ws-events.md §"Test surface" (T-001, T-005).
# ---------------------------------------------------------------------------


async def test_log_admin_action_broadcasts_within_two_seconds(
    pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ws-events.md T-001: broadcast fires within 2s of the durable INSERT."""

    captured: list[float] = []

    async def _record(_session_id: str, _message: dict, *, allow_roles: frozenset[str]) -> None:
        captured.append(asyncio.get_event_loop().time())
        del allow_roles  # role-filter is covered elsewhere

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", _record)

    session_id, facilitator_id = await _insert_session(pool)
    repo = LogRepository(pool)
    started = asyncio.get_event_loop().time()
    await repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="remove_participant",
        target_id=facilitator_id,
        broadcast_session_id=session_id,
    )

    # log_admin_action fires the legacy + spec-029 broadcasts inline
    # before returning; both timestamps land before this point.
    assert captured, "broadcast helper MUST fire when broadcast_session_id is set"
    elapsed = max(captured) - started
    assert elapsed < 2.0, f"broadcast latency {elapsed}s exceeds 2s SC budget"


async def test_audit_event_id_is_stable_across_endpoint_and_broadcast(
    pool: asyncpg.Pool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ws-events.md T-005: the SPA can dedup on row.id when both paths fire.

    Verifies that the ``id`` column in the WS payload matches the ``id``
    the FR-001 endpoint returns for the same insertion. The frontend
    uses this invariant to dedup an in-flight HTTP refetch against a WS
    push of the same row.
    """

    captured_payloads: list[dict] = []

    async def _record(_session_id: str, message: dict, *, allow_roles: frozenset[str]) -> None:
        if message.get("type") == "audit_log_appended":
            captured_payloads.append(message["payload"])
        del allow_roles

    monkeypatch.setattr("src.web_ui.websocket.broadcast_to_session_roles", _record)

    session_id, facilitator_id = await _insert_session(pool)
    repo = LogRepository(pool)
    entry = await repo.log_admin_action(
        session_id=session_id,
        facilitator_id=facilitator_id,
        action="remove_participant",
        target_id=facilitator_id,
        broadcast_session_id=session_id,
    )

    page = await repo.get_audit_log_page(session_id, offset=0, limit=10)
    assert len(page.rows) == 1
    endpoint_id = page.rows[0].id
    assert captured_payloads, "spec 029 broadcast MUST fire"
    assert captured_payloads[0]["id"] == entry.id == endpoint_id
