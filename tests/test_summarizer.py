"""US1-5: Summarization checkpoints — trigger, JSON, fallback, storage."""

from __future__ import annotations

import json
from types import SimpleNamespace

import asyncpg
import pytest
from cryptography.fernet import Fernet

from src.orchestrator import summarizer as summarizer_mod
from src.orchestrator.summarizer import (
    SummarizationManager,
    _fetch_turns_since,
    _generate_summary,
    _narrative_fallback,
    _normalize_summary,
    _validate_summary_json,
)
from src.repositories.errors import ProviderDispatchError
from src.repositories.message_repo import MessageRepository
from src.repositories.session_repo import SessionRepository


def test_should_summarize_at_threshold() -> None:
    """Trigger fires when threshold reached."""
    mgr = SummarizationManager.__new__(SummarizationManager)
    mgr._threshold = 50
    assert mgr.should_summarize(50, 0) is True
    assert mgr.should_summarize(100, 50) is True


def test_should_not_summarize_early() -> None:
    """Trigger does not fire before threshold."""
    mgr = SummarizationManager.__new__(SummarizationManager)
    mgr._threshold = 50
    assert mgr.should_summarize(49, 0) is False
    assert mgr.should_summarize(30, 0) is False


def test_configurable_threshold() -> None:
    """Different thresholds work correctly."""
    mgr = SummarizationManager.__new__(SummarizationManager)
    mgr._threshold = 30
    assert mgr.should_summarize(30, 0) is True
    assert mgr.should_summarize(29, 0) is False


def test_validate_valid_json() -> None:
    """Valid JSON with all fields parses correctly."""
    content = json.dumps(
        {
            "decisions": [{"turn": 1, "summary": "x", "status": "accepted"}],
            "open_questions": [{"turn": 2, "summary": "y"}],
            "key_positions": [{"participant": "A", "position": "z"}],
            "narrative": "Overview text",
        }
    )
    result = _validate_summary_json(content)
    assert result is not None
    assert len(result["decisions"]) == 1
    assert result["narrative"] == "Overview text"


def test_validate_invalid_json_returns_none() -> None:
    """Invalid JSON returns None."""
    assert _validate_summary_json("not json {") is None
    assert _validate_summary_json("") is None


def test_normalize_fills_missing_fields() -> None:
    """Missing fields default to empty arrays/strings."""
    result = _normalize_summary({"narrative": "Just a story"})
    assert result["decisions"] == []
    assert result["open_questions"] == []
    assert result["key_positions"] == []
    assert result["narrative"] == "Just a story"


def test_normalize_preserves_existing_fields() -> None:
    """Existing fields are preserved."""
    data = {
        "decisions": [{"turn": 1, "summary": "x", "status": "ok"}],
        "open_questions": [],
        "key_positions": [],
        "narrative": "text",
    }
    result = _normalize_summary(data)
    assert len(result["decisions"]) == 1


def test_narrative_fallback_wraps_raw() -> None:
    """Narrative fallback wraps raw text in valid JSON."""
    raw = "This is just raw text from the model."
    result = json.loads(_narrative_fallback(raw))
    assert result["narrative"] == raw
    assert result["decisions"] == []
    assert result["open_questions"] == []


def test_narrative_fallback_is_valid_json() -> None:
    """Narrative fallback produces parseable JSON."""
    result = _narrative_fallback("Any text here")
    parsed = json.loads(result)
    assert "narrative" in parsed


@pytest.fixture
async def _summary_session(pool: asyncpg.Pool) -> tuple[str, str, str]:
    """Create a session + branch; return (session_id, speaker_id, branch_id)."""
    repo = SessionRepository(pool)
    session, participant, branch = await repo.create_session(
        "Summary Loop Test",
        facilitator_display_name="Alice",
        facilitator_provider="anthropic",
        facilitator_model="claude-sonnet-4-20250514",
        facilitator_model_tier="high",
        facilitator_model_family="claude",
        facilitator_context_window=200000,
    )
    return session.id, participant.id, branch.id


def _stub_participant(model: str) -> SimpleNamespace:
    return SimpleNamespace(model=model, api_key_encrypted=None, api_endpoint=None)


_VALID_SUMMARY_JSON = json.dumps(
    {"decisions": [], "open_questions": [], "key_positions": [], "narrative": "ok"}
)


@pytest.mark.asyncio
async def test_generate_summary_falls_back_to_next_cheapest(monkeypatch) -> None:
    """Round09: cheapest AI on dead quota → use next-cheapest, no 500."""
    calls: list[str] = []

    async def fake_dispatch(*, model, **kwargs):
        calls.append(model)
        if model == "gemini/gemini-2.0-flash-lite-001":
            raise ProviderDispatchError("simulated 429")
        return SimpleNamespace(content=_VALID_SUMMARY_JSON)

    monkeypatch.setattr(summarizer_mod, "dispatch_with_retry", fake_dispatch)
    cheapest = _stub_participant("gemini/gemini-2.0-flash-lite-001")
    fallback = _stub_participant("anthropic/claude-haiku-4-5-20251001")
    out = await _generate_summary(turns=[], candidates=[cheapest, fallback], encryption_key="k")
    assert calls == [cheapest.model, fallback.model]
    assert json.loads(out)["narrative"] == "ok"


@pytest.mark.asyncio
async def test_generate_summary_raises_when_all_candidates_fail(monkeypatch) -> None:
    """Every candidate dies → re-raise so the 500 path still fires."""

    async def fake_dispatch(*, model, **kwargs):
        raise ProviderDispatchError(f"down: {model}")

    monkeypatch.setattr(summarizer_mod, "dispatch_with_retry", fake_dispatch)
    candidates = [_stub_participant("m1"), _stub_participant("m2")]
    with pytest.raises(ProviderDispatchError):
        await _generate_summary(turns=[], candidates=candidates, encryption_key="k")


async def test_fetch_turns_since_excludes_prior_summaries(
    pool: asyncpg.Pool,
    _summary_session: tuple[str, str, str],
) -> None:
    """Regression: Test06-Web06 loop where summaries re-summarized themselves."""
    session_id, speaker_id, branch_id = _summary_session
    msg_repo = MessageRepository(pool)
    base = {
        "session_id": session_id,
        "branch_id": branch_id,
        "speaker_id": speaker_id,
        "token_count": 1,
        "complexity_score": "low",
    }
    await msg_repo.append_message(**base, speaker_type="ai", content="real AI turn")
    await msg_repo.append_message(
        **base, speaker_type="summary", content='{"n":"prior"}', summary_epoch=0
    )
    turns = await _fetch_turns_since(msg_repo, pool, session_id, last_summary_turn=-1)
    contents = [t.content for t in turns]
    assert any("real AI turn" in c for c in contents)
    assert not any("prior" in c for c in contents)
    _ = Fernet.generate_key()  # hush unused-import warning
