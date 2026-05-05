"""Tests for src/operations/retention_purge.py — 007 §SC-009 purge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from src.operations.retention_purge import purge_security_events
from src.repositories.session_repo import SessionRepository


async def _make_session_speaker(pool: asyncpg.Pool) -> tuple[str, str]:
    session, facilitator, _ = await SessionRepository(pool).create_session(
        "Retention Purge Test",
        facilitator_display_name="Facilitator",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    return session.id, facilitator.id


async def _seed_event(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    speaker_id: str,
    days_old: float,
) -> None:
    when = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_old)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO security_events
              (session_id, speaker_id, turn_number, layer, risk_score,
               findings, blocked, timestamp)
            VALUES ($1, $2, 0, 'sanitizer', 0.0, '[]', false, $3)
            """,
            session_id,
            speaker_id,
            when,
        )


async def test_sc009_purge_deletes_rows_older_than_retention(pool: asyncpg.Pool) -> None:
    """Rows older than retention_days are deleted; fresh rows survive."""
    sid, pid = await _make_session_speaker(pool)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=120.0)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=95.0)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=30.0)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=1.0)

    deleted = await purge_security_events(pool, retention_days=90)

    assert deleted == 2
    async with pool.acquire() as conn:
        remaining = await conn.fetchval("SELECT COUNT(*) FROM security_events")
    assert remaining == 2


async def test_sc009_purge_returns_zero_when_no_aged_rows(pool: asyncpg.Pool) -> None:
    """Empty / all-fresh table → zero deletions, no-op."""
    sid, pid = await _make_session_speaker(pool)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=10.0)

    deleted = await purge_security_events(pool, retention_days=90)
    assert deleted == 0


async def test_sc009_purge_respects_custom_retention_window(pool: asyncpg.Pool) -> None:
    """Operator-tightened retention deletes more rows."""
    sid, pid = await _make_session_speaker(pool)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=15.0)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=8.0)
    await _seed_event(pool, session_id=sid, speaker_id=pid, days_old=2.0)

    deleted = await purge_security_events(pool, retention_days=7)
    assert deleted == 2


async def test_sc009_purge_rejects_non_positive_retention() -> None:
    """retention_days <= 0 is a programmer error; refuse with ValueError before touching pool."""
    with pytest.raises(ValueError, match="retention_days must be > 0"):
        await purge_security_events(pool=None, retention_days=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="retention_days must be > 0"):
        await purge_security_events(pool=None, retention_days=-1)  # type: ignore[arg-type]


def test_cli_retention_days_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI defaults to 90 days when SACP_SECURITY_EVENTS_RETENTION_DAYS is unset."""
    import sys

    sys.path.insert(0, "scripts")
    try:
        from purge_security_events import _retention_days

        monkeypatch.delenv("SACP_SECURITY_EVENTS_RETENTION_DAYS", raising=False)
        assert _retention_days(None) == 90
    finally:
        sys.path.pop(0)


def test_cli_retention_days_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI honors SACP_SECURITY_EVENTS_RETENTION_DAYS when set."""
    import sys

    sys.path.insert(0, "scripts")
    try:
        from purge_security_events import _retention_days

        monkeypatch.setenv("SACP_SECURITY_EVENTS_RETENTION_DAYS", "30")
        assert _retention_days(None) == 30
    finally:
        sys.path.pop(0)


def test_cli_retention_days_arg_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """--retention-days flag overrides the env var for ad-hoc operator runs."""
    import sys

    sys.path.insert(0, "scripts")
    try:
        from purge_security_events import _retention_days

        monkeypatch.setenv("SACP_SECURITY_EVENTS_RETENTION_DAYS", "30")
        assert _retention_days(7) == 7
    finally:
        sys.path.pop(0)
