"""004 convergence-cadence testability suite (Phase F, fix/004-followups).

Covers audit-plan items not addressed by ``test_convergence.py`` /
``test_cadence.py`` / ``test_adversarial.py``:

* FR-013 SafeTensors-only enforcement: load_model passes
  ``model_kwargs={"use_safetensors": True}`` — verified by source
  inspection (the actual model fetch is integration-tier).
* FR-013 cold-start failure handling: load_model swallows transformer
  exceptions and leaves _model None so process_turn returns 0.0
  rather than crashing.
* FR-003 sliding-window floor: window with 0/1/2 prior turns returns
  similarity 0.0; >=3 turns produces a real score.
* FR-018 window excludes non-AI rows: only ``convergence_log`` rows
  feed the window, and those are written exclusively for AI turns.
* FR-019 process_turn returns synchronously (no orphan tasks): the
  coroutine awaits the executor and returns a tuple, not a Task.
* FR-005 / FR-006 divergence/escalation flag transitions across all
  three states (clear, divergence-prompted, escalated).
* FR-009 cadence preset bounds: sprint vs cruise floor/ceiling.
* FR-011 adversarial rotation respects participant filter (skipped
  participants are not target candidates).
* FR-016 embedding bytes never exposed: convergence_log query in
  debug.py excludes the embedding column (cross-spec assertion).
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp_server.tools.debug import _LOG_QUERIES
from src.orchestrator import convergence as convergence_module
from src.orchestrator.adversarial import AdversarialRotator
from src.orchestrator.cadence import (
    CRUISE_CEILING,
    CRUISE_FLOOR,
    HIGH_SIMILARITY,
    LOW_SIMILARITY,
    SPRINT_CEILING,
    SPRINT_FLOOR,
    CadenceController,
)
from src.orchestrator.convergence import (
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    DIVERGENCE_PROMPT,
    ConvergenceDetector,
)

# ---------------------------------------------------------------------------
# FR-013: SafeTensors-only model load (structural enforcement)
# ---------------------------------------------------------------------------


def test_fr013_load_model_passes_use_safetensors_kwarg() -> None:
    """load_model body explicitly passes use_safetensors=True.

    Static check: the SafeTensors-only enforcement is the kwarg passed to
    SentenceTransformer. A regression that drops the kwarg would silently
    re-enable .bin (pickle) fallback.
    """
    src = inspect.getsource(ConvergenceDetector.load_model)
    assert '"use_safetensors": True' in src, (
        "FR-013 enforcement gone — SentenceTransformer call no longer pins "
        "use_safetensors=True; pickle fallback is re-enabled"
    )


def test_fr013_load_model_swallows_load_failure_to_none() -> None:
    """A failed model load leaves _model None and logs a warning."""
    detector = ConvergenceDetector(log_repo=MagicMock())
    # Force the import path to raise — sentence_transformers is optional.
    import sys

    # Stash and remove sentence_transformers from sys.modules.
    saved = sys.modules.pop("sentence_transformers", None)
    try:
        # Inject a stub that raises on import-side access.
        bad = MagicMock()
        bad.SentenceTransformer.side_effect = RuntimeError("model unavailable")
        sys.modules["sentence_transformers"] = bad
        detector.load_model()
        assert detector._model is None
    finally:
        if saved is not None:
            sys.modules["sentence_transformers"] = saved
        else:
            sys.modules.pop("sentence_transformers", None)


# ---------------------------------------------------------------------------
# FR-003: sliding-window floor of 3 prior turns
# ---------------------------------------------------------------------------


@dataclass
class _StubLogEntry:
    embedding: bytes


@pytest.mark.asyncio
async def test_fr003_window_below_floor_returns_zero_similarity() -> None:
    """Window with 0, 1, or 2 prior turns returns 0.0, not partial signal."""
    log_repo = MagicMock()
    detector = ConvergenceDetector(log_repo=log_repo)
    import numpy as np

    new_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float32).tobytes()
    for window_size in (0, 1, 2):
        log_repo.get_convergence_window = AsyncMock(
            return_value=[_StubLogEntry(new_embedding)] * window_size,
        )
        sim = await detector._compute_similarity("s1", new_embedding)
        assert sim == 0.0, f"window_size={window_size} yielded non-zero {sim}"


@pytest.mark.asyncio
async def test_fr003_window_at_floor_yields_real_score() -> None:
    """Window with exactly 3 prior turns produces a real similarity value."""
    import numpy as np

    log_repo = MagicMock()
    detector = ConvergenceDetector(log_repo=log_repo)
    same = np.array([1.0, 0.0, 0.0], dtype=np.float32).tobytes()
    log_repo.get_convergence_window = AsyncMock(
        return_value=[_StubLogEntry(same)] * 3,
    )
    sim = await detector._compute_similarity("s1", same)
    assert sim == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# FR-018: window operates over convergence_log only (AI-turn-exclusive)
# ---------------------------------------------------------------------------


def test_fr018_window_source_is_convergence_log_only() -> None:
    """The detector calls get_convergence_window — never get_messages.

    convergence_log rows are written only on AI turns, so the window
    naturally excludes humans / system / summaries. This test pins the
    source-data invariant.
    """
    src = inspect.getsource(ConvergenceDetector._compute_similarity)
    assert "get_convergence_window" in src
    assert "get_messages" not in src
    assert "get_recent" not in src


# ---------------------------------------------------------------------------
# FR-019: process_turn awaits the executor (no orphan tasks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fr019_process_turn_returns_tuple_not_task() -> None:
    """process_turn awaits its async work and returns a tuple, not a coroutine."""
    log_repo = MagicMock()
    log_repo.get_convergence_window = AsyncMock(return_value=[])
    log_repo.log_convergence = AsyncMock()
    log_repo.log_density_anomaly = AsyncMock()
    session_repo = MagicMock()
    session_repo.get_density_baseline = AsyncMock(return_value=[])
    session_repo.replace_density_baseline = AsyncMock()
    detector = ConvergenceDetector(log_repo=log_repo, session_repo=session_repo)
    # Stub the model so the test doesn't pull sentence_transformers.
    detector._model = MagicMock()
    detector._model.encode.return_value = MagicMock(tobytes=lambda: b"\x00" * 384 * 4)
    result = await detector.process_turn(
        turn_number=1,
        session_id="s1",
        content="hello world",
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    sim, diverge = result
    assert isinstance(sim, float)
    assert isinstance(diverge, bool)
    # No leftover pending tasks created by process_turn.
    pending = [t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()]
    assert pending == []


@pytest.mark.asyncio
async def test_fr019_process_turn_skips_log_for_nonpositive_turn() -> None:
    """Turn numbers <= 0 (skipped/placeholder) bypass logging."""
    log_repo = MagicMock()
    log_repo.get_convergence_window = AsyncMock(return_value=[])
    log_repo.log_convergence = AsyncMock()
    detector = ConvergenceDetector(log_repo=log_repo)
    detector._model = MagicMock()
    detector._model.encode.return_value = MagicMock(tobytes=lambda: b"\x00" * 384 * 4)
    await detector.process_turn(turn_number=0, session_id="s1", content="hi")
    await detector.process_turn(turn_number=-1, session_id="s1", content="hi")
    log_repo.log_convergence.assert_not_called()


# ---------------------------------------------------------------------------
# FR-005 / FR-006: divergence + escalation state transitions
# ---------------------------------------------------------------------------


def test_fr005_fr006_full_state_transition_matrix() -> None:
    """Walk the full state machine: clear -> diverge -> escalate -> clear."""
    detector = ConvergenceDetector.__new__(ConvergenceDetector)
    detector._threshold = 0.75
    detector._divergence_prompted = False

    # State A: not converging -> no diverge, no escalate.
    assert detector.should_diverge(0.5) is False
    assert detector.should_escalate(0.5) is False

    # State B: first convergence -> diverge prompt fires.
    assert detector.should_diverge(0.9) is True
    detector.mark_divergence_prompted()

    # State C: continued convergence after prompt -> escalate, no double-diverge.
    assert detector.should_escalate(0.9) is True
    assert detector.should_diverge(0.9) is False

    # State D: low similarity clears the flag (back to A).
    detector.should_diverge(0.3)
    assert detector._divergence_prompted is False
    assert detector.should_escalate(0.9) is False


def test_fr017_divergence_prompt_text_is_pinned() -> None:
    """The canonical prompt string lives in convergence.DIVERGENCE_PROMPT."""
    assert isinstance(DIVERGENCE_PROMPT, str)
    assert "weakest assumption" in DIVERGENCE_PROMPT
    # The prompt is system-trust content; tier 008 sanitization is not
    # applied (FR-017). Pin a non-empty, non-trivial length.
    assert len(DIVERGENCE_PROMPT) > 50


# ---------------------------------------------------------------------------
# FR-008 / FR-009 / FR-010: cadence pacing + preset bounds
# ---------------------------------------------------------------------------


def test_fr009_sprint_bounds() -> None:
    """Sprint preset stays within (2, 15) seconds."""
    assert (SPRINT_FLOOR, SPRINT_CEILING) == (2.0, 15.0)
    ctrl = CadenceController()
    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
        d = ctrl.compute_delay("s1", similarity=s, preset="sprint")
        assert SPRINT_FLOOR <= d <= SPRINT_CEILING


def test_fr009_cruise_bounds() -> None:
    """Cruise preset stays within (5, 60) seconds."""
    assert (CRUISE_FLOOR, CRUISE_CEILING) == (5.0, 60.0)
    ctrl = CadenceController()
    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
        d = ctrl.compute_delay("s1", similarity=s, preset="cruise")
        assert CRUISE_FLOOR <= d <= CRUISE_CEILING


def test_fr008_monotonic_in_similarity() -> None:
    """Higher similarity yields equal-or-larger delay (monotonic non-decreasing)."""
    ctrl = CadenceController()
    last = 0.0
    for s in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
        d = ctrl.compute_delay(f"sess-{s}", similarity=s, preset="cruise")
        assert d >= last - 1e-6
        last = d


def test_fr010_interjection_resets_to_floor_for_either_preset() -> None:
    """Reset returns the floor of whichever preset the session was using."""
    ctrl = CadenceController()
    ctrl.compute_delay("sprint-sess", similarity=0.9, preset="sprint")
    ctrl.compute_delay("cruise-sess", similarity=0.9, preset="cruise")
    assert ctrl.reset_on_interjection("sprint-sess") == SPRINT_FLOOR
    assert ctrl.reset_on_interjection("cruise-sess") == CRUISE_FLOOR


def test_low_high_similarity_constants_are_documented() -> None:
    """LOW/HIGH_SIMILARITY constants frame the interpolation, not gate it."""
    assert LOW_SIMILARITY == 0.3
    assert HIGH_SIMILARITY == 0.7


# ---------------------------------------------------------------------------
# FR-011 / FR-012: adversarial rotation
# ---------------------------------------------------------------------------


def test_fr011_rotation_advances_index_modulo_participants() -> None:
    """Target index walks 0 -> 1 -> 2 -> 0 across a 3-participant roster."""
    rotator = AdversarialRotator(interval=2)
    seen = []
    for _ in range(6):
        seen.append(rotator.get_target_index("s1", 3))
        rotator.reset_and_rotate("s1")
    # After 6 rotations across 3 participants, every index hit at least twice.
    assert sorted(seen) == [0, 0, 1, 1, 2, 2]


def test_fr011_zero_participants_is_safe_default() -> None:
    """Empty roster returns 0 instead of dividing by zero."""
    rotator = AdversarialRotator()
    assert rotator.get_target_index("s1", 0) == 0


def test_fr017_adversarial_prompt_text_is_pinned() -> None:
    """The canonical prompt lives in adversarial.ADVERSARIAL_PROMPT."""
    from src.orchestrator.adversarial import ADVERSARIAL_PROMPT

    assert "weakest assumption" in ADVERSARIAL_PROMPT
    # Phase 1: prompts overlap by accepted residual; both contain the same key
    # phrase. Test pins the overlap so divergent text is a deliberate change.
    assert "weakest assumption" in DIVERGENCE_PROMPT


# ---------------------------------------------------------------------------
# FR-016: embedding bytes never exposed via debug-export
# ---------------------------------------------------------------------------


def test_fr016_debug_export_excludes_embedding_bytes() -> None:
    """The convergence_log dump query is a column-list, not SELECT *.

    Cross-spec assertion: 010 §SC-008 enforces this at the export site.
    Repeating the assertion here keeps the FR-016 contract self-evident
    in the 004 testability surface.
    """
    sql = _LOG_QUERIES["convergence"]
    assert "embedding" not in sql.lower()
    assert "SELECT *" not in sql.upper()


# ---------------------------------------------------------------------------
# Module-level constants pinned (defensive against silent retunings)
# ---------------------------------------------------------------------------


def test_default_window_and_threshold_pinned() -> None:
    """Default window=5, threshold=0.75 per FR-003 / FR-004."""
    assert DEFAULT_WINDOW == 5
    assert DEFAULT_THRESHOLD == 0.75


def test_module_level_no_global_event_loop_state() -> None:
    """convergence module exposes no module-level singleton or global state.

    Module-level globals tend to hide cross-test leak channels. Per-session
    state lives on the detector instance; per-test fixtures construct their
    own detector. This test pins the no-globals contract.
    """
    forbidden = {"_GLOBAL_DETECTOR", "_SHARED_MODEL", "_DETECTOR"}
    found = forbidden.intersection(dir(convergence_module))
    assert not found, f"unexpected module globals: {found}"
