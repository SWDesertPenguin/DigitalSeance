# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 SC-002 regression canary (T017 of tasks.md).

Architectural assertion: when ``SACP_RESPONSE_SHAPING_ENABLED`` is unset
or ``false``, NO spec 021 shaping code path fires. Pre-feature loop
behavior is preserved byte-identically at the user-facing layer (message
content, dispatch counts, cost values, audit-log content) per
spec.md §SC-002.

This canary lands EARLY per plan.md "Notes for /speckit.tasks" — it acts
as a leak detector before US-phase code grows. The current shape pins
the architectural invariants that hold today and that every Phase 3+
task MUST preserve under master-switch-off:

1. The master-switch validator accepts unset/empty/'false'/'0'/'False'
   as "off" without raising — and a process running with the env unset
   sees no shaping behavior.
2. The orchestrator loop module does NOT import any symbol from
   ``src.orchestrator.shaping`` or ``src.prompts.register_presets``
   unconditionally at module load. (Phase 3 will add the post-dispatch
   wiring guarded by the master-switch read; this canary tightens to
   "loop.py imports the shaping module but the shaping path is
   short-circuited when the switch is off" once T029 lands.)
3. The five new ``routing_log`` columns added by alembic 013 exist on
   the table schema but the orchestrator loop does NOT populate them
   from any current code path. Their column names must NOT appear in
   ``log_routing`` parameter lists or insert SQL today.
4. ``ConvergenceDetector.last_embedding`` and ``recent_embeddings``
   (the spec 004 hook landed by T013) are read-only properties — they
   expose state but do not themselves invoke any shaping logic.

As US-phase code lands, this file gains corresponding architectural
assertions (e.g., once ``evaluate_and_maybe_retry`` exists in T028, this
canary asserts it is NOT called from ``execute_turn`` paths when the
switch is off — verified via a monkeypatch that fails the test if the
function fires under disabled mode). Until then the absence-of-wiring
assertions are the canary.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import src.auth  # noqa: F401  # prime auth package against loop.py circular
from src.config import validators
from src.orchestrator import convergence as convergence_module
from src.orchestrator import loop as loop_module
from src.orchestrator import shaping as shaping_module
from src.prompts import register_presets as register_presets_module
from src.repositories import log_repo as log_repo_module

REPO_ROOT = Path(__file__).resolve().parent.parent

# The five routing_log columns added by alembic 013 (T012). Master-switch-off
# means none of these columns may be populated by any current orchestrator
# code path. The schema-mirror DDL still defines the columns (NULL-default)
# per FR-005 / SC-002 wording — their presence is allowed, their being
# referenced from log_routing call sites today is not.
_NEW_ROUTING_LOG_COLUMNS = (
    "shaping_score_ms",
    "shaping_retry_dispatch_ms",
    "filler_score",
    "shaping_retry_delta_text",
    "shaping_reason",
)


@pytest.fixture(autouse=True)
def _switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the master switch unset (functionally off)."""
    monkeypatch.delenv("SACP_RESPONSE_SHAPING_ENABLED", raising=False)


# ---------------------------------------------------------------------------
# Validator accepts the off states without raising — process can boot
# ---------------------------------------------------------------------------


def test_master_switch_unset_passes_validator() -> None:
    """SC-002 / FR-005: unset env var means master switch is off; validator passes."""
    assert validators.validate_response_shaping_enabled() is None


@pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", ""])
def test_master_switch_off_values_pass_validator(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    """Each valid 'off' value clears the V16 gate; nothing here implies activation."""
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", value)
    assert validators.validate_response_shaping_enabled() is None


# ---------------------------------------------------------------------------
# Orchestrator loop has no shaping imports today
# ---------------------------------------------------------------------------


def test_loop_module_does_not_import_shaping() -> None:
    """No spec 021 shaping symbols are bound at loop-module load.

    Phase 3 (T029) will add the ``evaluate_and_maybe_retry`` call site,
    guarded by a master-switch read. This canary asserts the pre-wiring
    state: no shaping-module attribute is currently visible from
    ``loop_module.__dict__``. When T029 lands, the assertion tightens to
    "shaping symbols are imported but the call is guarded by the switch."
    """
    leaked = [
        name
        for name in dir(loop_module)
        if name.startswith(("compute_filler_score", "evaluate_and_maybe_retry"))
    ]
    assert not leaked, (
        f"SC-002 leak: loop.py exposes shaping symbols pre-T029: {leaked}. "
        "Wiring landed before the master-switch guard."
    )


def test_loop_module_does_not_import_register_presets() -> None:
    """RegisterPreset symbols belong in the prompt-assembly path (US2 T042).

    Until that wiring lands they MUST NOT appear at loop-module load —
    the slider is a prompt-composition concern, but the wire-in point
    is ``src.prompts.tiers.assemble_prompt``, not ``loop.py`` directly.
    """
    leaked = [
        name
        for name in dir(loop_module)
        if name in ("REGISTER_PRESETS", "preset_for_slider", "preset_for_name")
    ]
    assert not leaked, f"SC-002 leak: loop.py exposes register-preset symbols pre-T042: {leaked}."


# ---------------------------------------------------------------------------
# log_repo.log_routing does not yet plumb the new shaping columns
# ---------------------------------------------------------------------------


def test_log_routing_signature_excludes_shaping_columns() -> None:
    """T031 plumbs the five new shaping columns through ``log_routing``.

    Pre-T031: the function signature MUST NOT include any of the five
    new column names as keyword parameters. If it does, US1 wiring landed
    early and the master-switch guard hasn't been audited yet.
    """
    sig = inspect.signature(log_repo_module.LogRepository.log_routing)
    params = set(sig.parameters)
    leaked = [c for c in _NEW_ROUTING_LOG_COLUMNS if c in params]
    assert not leaked, (
        f"SC-002 leak: log_routing accepts shaping columns pre-T031: {leaked}. "
        "Plumbing landed before the master-switch guard."
    )


# ---------------------------------------------------------------------------
# Convergence hook is read-only (spec 004 hook is shape-only)
# ---------------------------------------------------------------------------


def test_convergence_hook_is_read_only() -> None:
    """T013 added ``last_embedding`` + ``recent_embeddings`` — both are property /
    helper reads only, not invocation points for shaping logic."""
    detector = convergence_module.ConvergenceDetector(log_repo=None)
    assert detector.last_embedding is None
    assert detector.recent_embeddings(depth=3) == []


def test_convergence_module_has_no_shaping_wiring() -> None:
    """``convergence.py`` MUST NOT import the shaping module — the data flow
    is the other direction (shaping reads convergence's exposed buffer)."""
    leaked = [
        name
        for name in dir(convergence_module)
        if name.startswith(("compute_filler_score", "evaluate_and_maybe_retry"))
        or name in ("BEHAVIORAL_PROFILES", "REGISTER_PRESETS")
    ]
    assert not leaked, f"SC-002 leak: convergence.py imports shaping symbols: {leaked}"


# ---------------------------------------------------------------------------
# Phase 2 modules are importable in isolation (no transitive shaping wire-in)
# ---------------------------------------------------------------------------


def test_shaping_module_exports_dataclasses_registry_and_orchestrator() -> None:
    """Phase 3 (US1) deliverable shape (T023-T028 landed): shaping.py exposes
    the BehavioralProfile registry, FillerScore / ShapingDecision dataclasses,
    the SHAPING_RETRY_CAP constant, the aggregator + scorer entry point, the
    per-family dispatch + threshold resolver, and the retry orchestrator.

    The presence of ``compute_filler_score`` / ``evaluate_and_maybe_retry`` /
    ``profile_for`` / ``threshold_for`` does NOT violate SC-002 on its own --
    SC-002 is about the dispatch path firing them. The master-switch guard
    lives at the call site (T029 in ``loop.py``); ``test_loop_module_does_not
    _import_shaping`` below pins that guard's pre-wiring state until T029
    lands and that canary tightens to "imports the module but the call is
    short-circuited when the switch is off".
    """
    public = {n for n in dir(shaping_module) if not n.startswith("_")}
    assert "BehavioralProfile" in public
    assert "BEHAVIORAL_PROFILES" in public
    assert "FillerScore" in public
    assert "ShapingDecision" in public
    assert "SHAPING_RETRY_CAP" in public
    # Phase 3 (T026-T028) implementation symbols are now present.
    for symbol in (
        "compute_filler_score",
        "evaluate_and_maybe_retry",
        "profile_for",
        "threshold_for",
    ):
        assert (
            symbol in public
        ), f"shaping.{symbol} expected after T026-T028 land; module shape regressed."


def test_register_presets_module_shape() -> None:
    """register_presets.py exposes the registry + lookups; no resolver here.

    The resolver lives in ``src/repositories/register_repo.py`` (US2 T039)
    so the registry stays a pure value module and the persistence /
    fallback chain stays in the repo layer.
    """
    public = {n for n in dir(register_presets_module) if not n.startswith("_")}
    assert "RegisterPreset" in public
    assert "REGISTER_PRESETS" in public
    assert "preset_for_slider" in public
    assert "preset_for_name" in public
    # The resolver is a US2 deliverable, not part of this module.
    assert "resolve_register" not in public
