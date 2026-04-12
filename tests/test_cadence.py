"""US3: Adaptive cadence — delay computation tests."""

from __future__ import annotations

from src.orchestrator.cadence import (
    CRUISE_CEILING,
    CRUISE_FLOOR,
    SPRINT_CEILING,
    SPRINT_FLOOR,
    CadenceController,
)


def test_low_similarity_low_delay_cruise() -> None:
    """Low similarity → delay near floor for cruise preset."""
    ctrl = CadenceController()
    delay = ctrl.compute_delay("s1", similarity=0.1, preset="cruise")
    assert delay < CRUISE_CEILING / 2


def test_high_similarity_high_delay_cruise() -> None:
    """High similarity → delay near ceiling for cruise preset."""
    ctrl = CadenceController()
    delay = ctrl.compute_delay("s1", similarity=0.9, preset="cruise")
    assert delay > CRUISE_CEILING / 2


def test_sprint_stays_within_bounds() -> None:
    """Sprint preset delays stay within sprint bounds."""
    ctrl = CadenceController()
    low = ctrl.compute_delay("s1", similarity=0.0, preset="sprint")
    high = ctrl.compute_delay("s1", similarity=1.0, preset="sprint")
    assert low >= SPRINT_FLOOR
    assert high <= SPRINT_CEILING


def test_cruise_stays_within_bounds() -> None:
    """Cruise preset delays stay within cruise bounds."""
    ctrl = CadenceController()
    low = ctrl.compute_delay("s1", similarity=0.0, preset="cruise")
    high = ctrl.compute_delay("s1", similarity=1.0, preset="cruise")
    assert low >= CRUISE_FLOOR
    assert high <= CRUISE_CEILING


def test_idle_returns_zero() -> None:
    """Idle preset returns 0 (trigger-only)."""
    ctrl = CadenceController()
    delay = ctrl.compute_delay("s1", similarity=0.5, preset="idle")
    assert delay == 0.0


def test_interjection_resets_to_floor() -> None:
    """Human interjection drops delay to floor."""
    ctrl = CadenceController()
    ctrl.compute_delay("s1", similarity=0.9, preset="cruise")
    reset = ctrl.reset_on_interjection("s1")
    assert reset == CRUISE_FLOOR
