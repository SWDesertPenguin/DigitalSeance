# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for src.orchestrator.signals — output detectors."""

from __future__ import annotations

import pytest

from src.orchestrator.signals import detect_exit_intent, extract_questions

# --- detect_exit_intent -------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        "I'm stepping back from this conversation.",
        "I'm not responding further in this thread.",
        "I am done responding.",
        "I'm bowing out for now.",
        "This conversation is over.",
        "I'll stop engaging.",
        "I will step away.",
        "I'm going silent.",
    ],
)
def test_detect_exit_intent_matches_canonical_phrases(content):
    assert detect_exit_intent(content) is not None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "I'm here and happy to keep helping.",
        "Let me explain why this isn't quite right.",
        "Stepping through the algorithm carefully...",  # 'stepping' alone
    ],
)
def test_detect_exit_intent_ignores_unrelated_text(content):
    assert detect_exit_intent(content) is None


def test_detect_exit_intent_returns_matched_phrase():
    phrase = detect_exit_intent("Look — I'm stepping back from this thread.")
    assert phrase is not None
    assert "stepping back" in phrase.lower()


# --- extract_questions --------------------------------------------------------


def _roster(*pairs) -> dict[str, dict[str, str]]:
    return {
        f"id{i}": {"id": f"id{i}", "display_name": n, "provider": p}
        for i, (n, p) in enumerate(pairs)
    }


def test_extract_questions_returns_empty_for_no_questions():
    assert extract_questions("This has no question marks.", _roster()) == []
    assert extract_questions("", _roster()) == []


def test_extract_questions_ignores_second_person_alone():
    # Second-person pronoun without a named human no longer triggers.
    out = extract_questions("Are you sure that's right?", _roster())
    assert out == []


def test_extract_questions_picks_up_named_human():
    roster = _roster(("Alice", "human"), ("Bot", "anthropic"))
    out = extract_questions("Alice, what do you think about the plan?", roster)
    assert len(out) == 1


def test_extract_questions_ignores_ai_to_ai_question():
    # A question naming only an AI participant should not fire.
    roster = _roster(("Alice", "human"), ("Bot", "anthropic"))
    out = extract_questions("Bot, what is your perspective on this?", roster)
    assert out == []


def test_extract_questions_skips_rhetorical_questions():
    # No second-person, no named participant → filtered out.
    out = extract_questions(
        "Why does this happen? Because the cache invalidates randomly.",
        _roster(("Alice", "human")),
    )
    assert out == []


def test_extract_questions_collects_multiple():
    roster = _roster(("Alice", "human"), ("Bob", "human"))
    out = extract_questions(
        "Alice, are you free? Bob, can you confirm the timing?",
        roster,
    )
    assert len(out) == 2


def test_extract_questions_handles_missing_roster():
    # No roster means no human names → no questions surfaced.
    out = extract_questions("Are you sure?", None)
    assert out == []
