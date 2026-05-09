# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 025 cap-decrease disambiguation helper (T044-T049 of tasks.md).

Pure-function tests for `detect_decrease_intent` — the FR-026 helper that
decides between a clean cap-set and a 409 disambiguation response. The
HTTP endpoint and the MCP tool variant share this helper per
research.md §7, so transport-agnostic correctness is verified here.

DB-gated end-to-end endpoint tests (HTTP 200/403/422/409 paths) are
deferred to Phase 8 integration tests (T090) since they need a real
FastAPI app + facilitator session.
"""

from __future__ import annotations

from src.orchestrator.length_cap import (
    CapUpdatePlan,
    DisambiguationRequired,
    detect_decrease_intent,
)

# ---------------------------------------------------------------------------
# Clean commits (no decrease, OR explicit interpretation, OR kind=none)
# ---------------------------------------------------------------------------


def test_first_time_cap_set_is_clean() -> None:
    """Setting a cap on a session with current_turn=0 is unambiguous."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=20,
        current_turns=0,
        current_seconds=0,
        interpretation=None,
    )
    assert isinstance(out, CapUpdatePlan)
    assert out.new_turns == 20
    assert out.interpretation is None


def test_cap_increase_is_clean() -> None:
    """Submitted > current_elapsed → no disambiguation."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=50,
        current_turns=12,
        current_seconds=0,
        interpretation=None,
    )
    assert isinstance(out, CapUpdatePlan)
    assert out.new_turns == 50


def test_clear_cap_is_always_clean() -> None:
    """kind='none' is unambiguous regardless of current elapsed."""
    out = detect_decrease_intent(
        submitted_kind="none",
        submitted_seconds=None,
        submitted_turns=None,
        current_turns=999,
        current_seconds=999,
        interpretation=None,
    )
    assert isinstance(out, CapUpdatePlan)
    assert out.new_kind == "none"


def test_explicit_absolute_skips_disambiguation() -> None:
    """Caller supplied interpretation='absolute' → commit as-is."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=20,
        current_turns=30,
        current_seconds=0,
        interpretation="absolute",
    )
    assert isinstance(out, CapUpdatePlan)
    assert out.new_turns == 20
    assert out.interpretation == "absolute"


def test_explicit_relative_computes_effective_cap() -> None:
    """Caller supplied interpretation='relative' → effective cap = current + submitted."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=20,
        current_turns=30,
        current_seconds=0,
        interpretation="relative",
    )
    assert isinstance(out, CapUpdatePlan)
    assert out.new_turns == 50  # 30 + 20
    assert out.interpretation == "relative"


# ---------------------------------------------------------------------------
# Disambiguation required (decrease without explicit interpretation)
# ---------------------------------------------------------------------------


def test_decrease_without_interpretation_returns_disambiguation() -> None:
    """Submitted=20 turns at current_turn=30 → both options surfaced."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=20,
        current_turns=30,
        current_seconds=0,
        interpretation=None,
    )
    assert isinstance(out, DisambiguationRequired)
    assert out.absolute_effective_turns == 20
    assert out.relative_effective_turns == 50  # 30 + 20


def test_disambiguation_carries_current_elapsed() -> None:
    """The 409 payload must surface the current elapsed counter for UX clarity."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=15,
        current_turns=25,
        current_seconds=0,
        interpretation=None,
    )
    assert isinstance(out, DisambiguationRequired)
    assert out.current_turns == 25


def test_decrease_at_exact_elapsed_still_disambiguates() -> None:
    """Submitted=20 at current=20 → 0 turns remaining; treat as decrease."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=20,
        current_turns=20,
        current_seconds=0,
        interpretation=None,
    )
    assert isinstance(out, DisambiguationRequired)


def test_time_decrease_disambiguates() -> None:
    """Time-cap decrease also triggers the 409 path."""
    out = detect_decrease_intent(
        submitted_kind="time",
        submitted_seconds=900,
        submitted_turns=None,
        current_turns=0,
        current_seconds=1500,
        interpretation=None,
    )
    assert isinstance(out, DisambiguationRequired)
    assert out.absolute_effective_seconds == 900
    assert out.relative_effective_seconds == 2400  # 1500 + 900


def test_both_dimensions_either_decrease_disambiguates() -> None:
    """When kind='both', a decrease on either dimension triggers 409."""
    # turns decrease only
    out = detect_decrease_intent(
        submitted_kind="both",
        submitted_seconds=3600,
        submitted_turns=10,
        current_turns=15,
        current_seconds=600,
        interpretation=None,
    )
    assert isinstance(out, DisambiguationRequired)


# ---------------------------------------------------------------------------
# Edge: no current elapsed but interpretation supplied (should still commit clean)
# ---------------------------------------------------------------------------


def test_interpretation_on_non_decrease_still_commits() -> None:
    """interpretation='absolute' on a non-decrease is harmless; commits as absolute."""
    out = detect_decrease_intent(
        submitted_kind="turns",
        submitted_seconds=None,
        submitted_turns=50,
        current_turns=10,
        current_seconds=0,
        interpretation="absolute",
    )
    assert isinstance(out, CapUpdatePlan)
    assert out.new_turns == 50
    assert out.interpretation == "absolute"
