# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR — CAPCOM prompt addendum (spec 008 coordination).

The addendum is appended to the CAPCOM AI's system prompt at assemble
time so the model knows its role + the two structured markers. Panel
AIs never see the addendum.
"""

from __future__ import annotations

from src.prompts.capcom_delta import CAPCOM_PROMPT_ADDENDUM, capcom_delta_for
from src.prompts.tiers import assemble_prompt


def test_addendum_emitted_when_participant_is_capcom():
    out = capcom_delta_for(is_capcom=True)
    assert out == CAPCOM_PROMPT_ADDENDUM
    assert "<capcom_relay>" in out
    assert "<capcom_query>" in out


def test_addendum_empty_for_panel_ai():
    assert capcom_delta_for(is_capcom=False) == ""


def test_assemble_prompt_threads_capcom_delta():
    prompt_with = assemble_prompt(
        prompt_tier="mid",
        capcom_delta=CAPCOM_PROMPT_ADDENDUM,
    )
    prompt_without = assemble_prompt(prompt_tier="mid")
    assert "capcom_relay" in prompt_with
    assert "capcom_relay" not in prompt_without


def test_addendum_documents_both_markers():
    """The model needs both markers documented to use them correctly."""
    assert "capcom_relay" in CAPCOM_PROMPT_ADDENDUM
    assert "capcom_query" in CAPCOM_PROMPT_ADDENDUM
    assert "wrap" in CAPCOM_PROMPT_ADDENDUM.lower()
