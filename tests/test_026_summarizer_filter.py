# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 T030 + T032 — summarizer corpus filter for density anomalies.

FR-019 strengthens spec 004's observational density signal into a filter
on the summarizer corpus: any turn whose ``convergence_log`` row carries
``tier='density_anomaly'`` MUST drop out of the rolling-summary input
list. The filter is a pure SQL discriminator against the existing
column shape (no schema change) and lives at the summarizer's
``_fetch_turns_since`` site.

The unit test below stubs ``MessageRepository.get_range`` + an asyncpg
pool that returns a known flagged-turn set, then asserts that the
resulting ``ContextMessage`` list excludes flagged turns and preserves
the rest in source order.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orchestrator.summarizer import _fetch_density_flagged_turns, _fetch_turns_since


@dataclass
class _StubMessage:
    """Minimal stand-in for the spec 001 messages row shape the summarizer reads."""

    turn_number: int
    speaker_type: str
    content: str


def _build_pool(flagged_turns: set[int]) -> MagicMock:
    """Build an asyncpg-pool mock that yields the flagged-turn set on the WHERE query."""

    async def _fetch(_sql: str, _session_id: str, *_args: object) -> list[dict[str, int]]:
        return [{"turn_number": t} for t in sorted(flagged_turns)]

    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=_fetch)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture(autouse=True)
def _patch_branch_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub get_main_branch_id to avoid a live-DB round-trip in the summarizer."""
    import src.orchestrator.summarizer as summarizer_mod

    async def _fake_branch(_pool: object, _session_id: str) -> str:
        return "main-branch"

    monkeypatch.setattr(summarizer_mod, "get_main_branch_id", _fake_branch)


@pytest.mark.asyncio
async def test_flagged_turn_drops_out_of_summarizer_corpus() -> None:
    """SC-005 / FR-019: density-flagged turn does NOT appear in the corpus."""
    pool = _build_pool({3})
    messages = [
        _StubMessage(turn_number=1, speaker_type="ai", content="alpha"),
        _StubMessage(turn_number=2, speaker_type="ai", content="beta"),
        _StubMessage(turn_number=3, speaker_type="ai", content="flagged-verbose"),
        _StubMessage(turn_number=4, speaker_type="ai", content="delta"),
    ]
    msg_repo = MagicMock()
    msg_repo.get_range = AsyncMock(return_value=messages)
    corpus = await _fetch_turns_since(msg_repo, pool, "sess-1", 0)
    assert [c.source_turn for c in corpus] == [1, 2, 4]
    assert "flagged-verbose" not in " ".join(c.content for c in corpus)


@pytest.mark.asyncio
async def test_no_flagged_turns_keeps_full_corpus() -> None:
    """Empty flagged set leaves the corpus untouched."""
    pool = _build_pool(set())
    messages = [
        _StubMessage(turn_number=1, speaker_type="ai", content="alpha"),
        _StubMessage(turn_number=2, speaker_type="ai", content="beta"),
    ]
    msg_repo = MagicMock()
    msg_repo.get_range = AsyncMock(return_value=messages)
    corpus = await _fetch_turns_since(msg_repo, pool, "sess-1", 0)
    assert [c.source_turn for c in corpus] == [1, 2]


@pytest.mark.asyncio
async def test_density_flagged_query_targets_session_and_range() -> None:
    """The flagged-turn query MUST scope to session_id + the turn range."""
    pool = _build_pool({7})
    flagged = await _fetch_density_flagged_turns(pool, "sess-z", 5, 10)
    assert flagged == frozenset({7})
    pool.acquire.return_value.__aenter__.return_value.fetch.assert_awaited_once()
    args = pool.acquire.return_value.__aenter__.return_value.fetch.await_args.args
    assert args[1] == "sess-z"
    assert args[2] == 5
    assert args[3] == 10
    sql = args[0]
    assert "convergence_log" in sql
    assert "tier = 'density_anomaly'" in sql


@pytest.mark.asyncio
async def test_multiple_flagged_turns_all_dropped() -> None:
    """Multiple density anomalies in the window all drop out of the corpus."""
    pool = _build_pool({2, 4})
    messages = [
        _StubMessage(turn_number=1, speaker_type="ai", content="a"),
        _StubMessage(turn_number=2, speaker_type="ai", content="b-flagged"),
        _StubMessage(turn_number=3, speaker_type="ai", content="c"),
        _StubMessage(turn_number=4, speaker_type="ai", content="d-flagged"),
        _StubMessage(turn_number=5, speaker_type="ai", content="e"),
    ]
    msg_repo = MagicMock()
    msg_repo.get_range = AsyncMock(return_value=messages)
    corpus = await _fetch_turns_since(msg_repo, pool, "sess-1", 0)
    assert [c.source_turn for c in corpus] == [1, 3, 5]
