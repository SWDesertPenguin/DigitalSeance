# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration: per-participant adapter resolution + reconcile drift report."""

from __future__ import annotations

from unittest.mock import patch

import asyncpg
import pytest

from src.api_bridge.tokenizer import (
    AnthropicTokenizer,
    OpenAITokenizer,
    clear_participant_cache,
    get_tokenizer_for_participant,
    reconcile_budget,
)


@pytest.fixture(autouse=True)
def _isolate_cache():
    clear_participant_cache()
    yield
    clear_participant_cache()


@pytest.mark.asyncio
async def test_factory_resolves_participant_model(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    _, _, participant, _ = session_with_participant
    tok = await get_tokenizer_for_participant(pool, participant.id)
    # Default test fixture uses an OpenAI participant
    assert isinstance(tok, OpenAITokenizer)


@pytest.mark.asyncio
async def test_factory_caches_per_participant(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    _, _, participant, _ = session_with_participant
    a = await get_tokenizer_for_participant(pool, participant.id)
    b = await get_tokenizer_for_participant(pool, participant.id)
    assert a is b


@pytest.mark.asyncio
async def test_factory_unknown_participant_returns_default(
    pool: asyncpg.Pool,
):
    tok = await get_tokenizer_for_participant(pool, "does-not-exist")
    assert tok.get_tokenizer_name() == "default:cl100k"


async def _seed_undercounted_messages(
    pool: asyncpg.Pool,
    session_id: str,
    branch_id: str,
    speaker_id: str,
    contents: list[str],
) -> None:
    from src.repositories.message_repo import MessageRepository

    repo = MessageRepository(pool)
    for content in contents:
        await repo.append_message(
            session_id=session_id,
            branch_id=branch_id,
            speaker_id=speaker_id,
            speaker_type="ai",
            content=content,
            token_count=1,
            complexity_score="low",
        )


@pytest.mark.asyncio
async def test_reconcile_budget_reports_drift(
    pool: asyncpg.Pool,
    session_with_participant: tuple,
):
    """Stored token_count deliberately undercounted; reconcile finds the drift."""
    session, _, participant, branch = session_with_participant
    contents = [
        "the quick brown fox jumps over the lazy dog",
        "second message with a few more interesting words",
        "third message which is somewhat longer than the others on purpose",
    ]
    await _seed_undercounted_messages(pool, session.id, branch.id, participant.id, contents)
    report = await reconcile_budget(pool, participant.id, api_key="unused-for-openai")
    assert report.participant_id == participant.id
    assert report.tokenizer_name.startswith("openai:")
    assert len(report.samples) == len(contents)
    assert report.cumulative_drift_pct > 0
    for sample in report.samples:
        assert sample["delta"] > 0
        assert sample["api_count"] > sample["stored"]


async def _create_anthropic_session(
    pool: asyncpg.Pool,
) -> tuple[object, object, object]:
    """Create a session with an Anthropic AI participant for SDK-fallback test."""
    from cryptography.fernet import Fernet

    from src.repositories.session_repo import SessionRepository

    enc_key = Fernet.generate_key().decode()
    session, _, branch = await SessionRepository(pool).create_session(
        "Anthropic test",
        facilitator_display_name="Fac",
        facilitator_provider="openai",
        facilitator_model="gpt-4o",
        facilitator_model_tier="high",
        facilitator_model_family="gpt",
        facilitator_context_window=128000,
    )
    participant = await _add_anthropic_participant(pool, session.id, enc_key)
    return session, participant, branch


async def _add_anthropic_participant(
    pool: asyncpg.Pool,
    session_id: str,
    enc_key: str,
) -> object:
    import uuid

    from src.repositories.participant_repo import ParticipantRepository

    p_repo = ParticipantRepository(pool, encryption_key=enc_key)
    participant, _ = await p_repo.add_participant(
        session_id=session_id,
        display_name="Claude",
        provider="anthropic",
        model="claude-3-5-sonnet",
        model_tier="high",
        model_family="claude",
        context_window=200000,
        api_key="sk-test",
        auth_token=uuid.uuid4().hex,
        auto_approve=True,
    )
    return participant


@pytest.mark.asyncio
async def test_reconcile_budget_anthropic_uses_fallback_when_sdk_missing(
    pool: asyncpg.Pool,
):
    """SDK-import failure on the reconcile path falls back to the in-process count."""
    session, participant, branch = await _create_anthropic_session(pool)
    await _seed_undercounted_messages(
        pool, session.id, branch.id, participant.id, ["brief test response"]
    )
    with patch.object(
        AnthropicTokenizer,
        "count_tokens_via_api",
        side_effect=RuntimeError("anthropic SDK not installed"),
    ):
        report = await reconcile_budget(pool, participant.id, api_key="sk-test")
    assert report.tokenizer_name.startswith("anthropic:")
    assert len(report.samples) == 1
