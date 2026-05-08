"""Spec 025 conclude-phase Tier 4 delta + cadence suspension (US1 acceptance #2 + #5).

Pure-function unit tests for the prompt-assembler and cadence-controller
extension points. Loop-integration acceptance scenarios that drive a
real session through to conclude phase + auto-pause + summarizer trigger
land in the Phase 8 integration test file (DB-gated, drives the full
`execute_turn` cycle).

Covers:

- US1 acceptance #2: Tier 4 conclude delta in next assembled prompt;
  participant `custom_prompt` and tier text preserved (FR-008/FR-009).
- US1 acceptance #5: spec 004 adaptive cadence suspended during conclude;
  preset floor returned (FR-010).
"""

from __future__ import annotations

from src.orchestrator.cadence import (
    CRUISE_FLOOR,
    SPRINT_FLOOR,
    CadenceController,
)
from src.prompts.conclude_delta import CONCLUDE_DELTA_TEXT, conclude_delta
from src.prompts.tiers import TIER_LOW, TIER_MID_DELTA, assemble_prompt

# ---------------------------------------------------------------------------
# US1 AC#2: conclude delta injected at Tier 4 additively
# ---------------------------------------------------------------------------


def test_conclude_delta_helper_active() -> None:
    assert conclude_delta(active=True) == CONCLUDE_DELTA_TEXT


def test_conclude_delta_helper_inactive() -> None:
    assert conclude_delta(active=False) == ""


def test_assemble_without_conclude_omits_delta() -> None:
    """Default: no conclude delta in the prompt (pre-feature behavior)."""
    out = assemble_prompt(prompt_tier="mid", custom_prompt="be terse")
    assert CONCLUDE_DELTA_TEXT not in out


def test_assemble_with_conclude_includes_delta() -> None:
    """FR-008: conclude delta appears in the assembled prompt."""
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt="be terse",
        conclude_delta=CONCLUDE_DELTA_TEXT,
    )
    assert CONCLUDE_DELTA_TEXT in out


def test_assemble_with_conclude_preserves_tier_text() -> None:
    """FR-009: conclude delta is additive — does NOT replace tier text."""
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt="be terse",
        conclude_delta=CONCLUDE_DELTA_TEXT,
    )
    assert TIER_LOW in out
    assert TIER_MID_DELTA in out


def test_assemble_with_conclude_preserves_custom_prompt() -> None:
    """FR-009: custom_prompt is also preserved alongside the conclude delta."""
    custom = "use bullet points only"
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt=custom,
        conclude_delta=CONCLUDE_DELTA_TEXT,
    )
    assert custom in out
    assert CONCLUDE_DELTA_TEXT in out


def test_conclude_delta_appears_after_custom_prompt() -> None:
    """Research §4 ordering: custom_prompt first, conclude delta last at Tier 4."""
    custom = "REGISTERED-CUSTOM-MARKER-XYZ"
    out = assemble_prompt(
        prompt_tier="mid",
        custom_prompt=custom,
        conclude_delta=CONCLUDE_DELTA_TEXT,
    )
    custom_pos = out.find(custom)
    conclude_pos = out.find(CONCLUDE_DELTA_TEXT)
    assert custom_pos != -1
    assert conclude_pos != -1
    assert conclude_pos > custom_pos


def test_empty_conclude_delta_is_a_noop() -> None:
    """Empty string disables injection — unchanged from default behavior."""
    a = assemble_prompt(prompt_tier="mid", custom_prompt="x")
    b = assemble_prompt(prompt_tier="mid", custom_prompt="x", conclude_delta="")
    # Canaries randomize the rendered output, but content tier blocks should match.
    assert TIER_LOW in a and TIER_LOW in b
    assert "x" in a and "x" in b
    assert CONCLUDE_DELTA_TEXT not in a
    assert CONCLUDE_DELTA_TEXT not in b


# ---------------------------------------------------------------------------
# US1 AC#5: cadence suspension during conclude (FR-010)
# ---------------------------------------------------------------------------


def test_cadence_running_default_uses_interpolation() -> None:
    """Pre-feature behavior: similarity drives delay between floor and ceiling."""
    cc = CadenceController()
    delay = cc.compute_delay("ses1", similarity=0.5, preset="cruise")
    assert delay > CRUISE_FLOOR  # interpolated above floor
    assert delay < 60.0  # below cruise ceiling


def test_cadence_conclude_phase_returns_floor_cruise() -> None:
    """FR-010: conclude phase suspends adaptive cadence; cruise floor returned."""
    cc = CadenceController()
    delay = cc.compute_delay("ses1", similarity=0.99, preset="cruise", phase="conclude")
    assert delay == CRUISE_FLOOR


def test_cadence_conclude_phase_returns_floor_sprint() -> None:
    """Same suspension behavior on sprint preset."""
    cc = CadenceController()
    delay = cc.compute_delay("ses1", similarity=0.99, preset="sprint", phase="conclude")
    assert delay == SPRINT_FLOOR


def test_cadence_conclude_phase_low_similarity_still_floor() -> None:
    """Even low-similarity (which would normally produce floor anyway) returns floor."""
    cc = CadenceController()
    delay = cc.compute_delay("ses1", similarity=0.0, preset="cruise", phase="conclude")
    assert delay == CRUISE_FLOOR


def test_cadence_conclude_then_running_resumes_interpolation() -> None:
    """US3 forward-compat: when phase reverts to 'running', adaptive cadence works again."""
    cc = CadenceController()
    cc.compute_delay("ses1", similarity=0.5, preset="cruise", phase="conclude")
    # Now back to running with high similarity should interpolate above floor.
    delay = cc.compute_delay("ses1", similarity=0.9, preset="cruise", phase="running")
    assert delay > CRUISE_FLOOR


def test_cadence_idle_preset_unaffected_by_phase() -> None:
    """preset='idle' returns 0.0 regardless of phase — trigger-only mode."""
    cc = CadenceController()
    assert cc.compute_delay("ses1", similarity=0.5, preset="idle", phase="conclude") == 0.0
    assert cc.compute_delay("ses1", similarity=0.5, preset="idle", phase="running") == 0.0
