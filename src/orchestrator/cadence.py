"""Adaptive cadence — similarity-based turn pacing."""

from __future__ import annotations

from dataclasses import dataclass

# Preset boundaries (seconds)
SPRINT_FLOOR = 2.0
SPRINT_CEILING = 15.0
CRUISE_FLOOR = 5.0
CRUISE_CEILING = 300.0  # 5 minutes

# Similarity thresholds for cadence adjustment
LOW_SIMILARITY = 0.3
HIGH_SIMILARITY = 0.7


@dataclass
class CadenceState:
    """Mutable cadence tracking per session."""

    preset: str
    current_delay: float
    last_similarity: float


class CadenceController:
    """Computes turn delay based on conversation similarity."""

    def __init__(self) -> None:
        self._states: dict[str, CadenceState] = {}

    def get_or_create(self, session_id: str, preset: str) -> CadenceState:
        """Get or create cadence state for a session."""
        if session_id not in self._states:
            floor, _ = _preset_bounds(preset)
            self._states[session_id] = CadenceState(
                preset=preset,
                current_delay=floor * 2,  # Start moderate
                last_similarity=0.0,
            )
        return self._states[session_id]

    def compute_delay(
        self,
        session_id: str,
        *,
        similarity: float,
        preset: str,
    ) -> float:
        """Compute delay from similarity and preset."""
        if preset == "idle":
            return 0.0  # Trigger-only, no auto-pacing
        state = self.get_or_create(session_id, preset)
        state.last_similarity = similarity
        floor, ceiling = _preset_bounds(preset)
        state.current_delay = _interpolate(similarity, floor, ceiling)
        return state.current_delay

    def reset_on_interjection(self, session_id: str) -> float:
        """Drop delay to floor on human interjection."""
        state = self._states.get(session_id)
        if state is None:
            return CRUISE_FLOOR
        floor, _ = _preset_bounds(state.preset)
        state.current_delay = floor
        return floor


def _preset_bounds(preset: str) -> tuple[float, float]:
    """Return (floor, ceiling) for a cadence preset."""
    if preset == "sprint":
        return SPRINT_FLOOR, SPRINT_CEILING
    return CRUISE_FLOOR, CRUISE_CEILING


def _interpolate(
    similarity: float,
    floor: float,
    ceiling: float,
) -> float:
    """Map similarity [0,1] to delay [floor, ceiling]."""
    clamped = max(0.0, min(1.0, similarity))
    return floor + clamped * (ceiling - floor)
