# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 register-preset registry — five canonical Tier 4 deltas.

Phase 2 deliverable (T015): frozen 1-5 mapping from slider value to
preset metadata. Lives as a module-level tuple-of-dataclasses; the
resolver and prompt-assembly hook (US2 / US3) consume the registry
unchanged. Per FR-007 / FR-013.

The registry is independent of ``SACP_RESPONSE_SHAPING_ENABLED`` per
spec edge case — slider deltas always emit regardless of master-switch
state because the slider is a prompt-composition concern, not a shaping
concern. The master switch only gates the filler-scorer + retry
pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisterPreset:
    """One register-preset entry — slider value, canonical name, Tier 4 delta.

    Per contracts/register-preset-interface.md and data-model.md
    "RegisterPreset". Frozen at module load.

    Fields:

    - ``slider``: integer in ``[1, 5]``.
    - ``name``: canonical preset name (snake_case): ``"direct"``,
      ``"conversational"``, ``"balanced"``, ``"technical"``,
      ``"academic"``.
    - ``tier4_delta``: delta text appended after the existing tier text
      and after any participant custom prompt; ``None`` for slider 3
      (Balanced — tier text alone) per FR-007 / FR-013.
    """

    slider: int
    name: str
    tier4_delta: str | None


# Canonical Tier 4 delta wording per FR-013 / data-model.md §RegisterPreset.
# Module-level tuple keyed by slider value via REGISTER_PRESETS[slider - 1].
REGISTER_PRESETS: tuple[RegisterPreset, ...] = (
    RegisterPreset(
        slider=1,
        name="direct",
        tier4_delta=("Reply briefly and directly. No preamble, no restatement, no closing."),
    ),
    RegisterPreset(
        slider=2,
        name="conversational",
        tier4_delta=(
            "Reply in a conversational register. Brief preamble"
            " acceptable; avoid academic register."
        ),
    ),
    RegisterPreset(
        slider=3,
        name="balanced",
        tier4_delta=None,
    ),
    RegisterPreset(
        slider=4,
        name="technical",
        tier4_delta=("Use precise technical register. Cite sources for non-obvious claims."),
    ),
    RegisterPreset(
        slider=5,
        name="academic",
        tier4_delta=(
            "Use formal academic register. Structured argumentation"
            " with explicit citations expected."
        ),
    ),
)


# Module-load invariant: the registry has exactly five entries indexed
# 1..5, each with a unique canonical name. Surface a misconfigured
# registry at import time rather than at runtime.
def _assert_registry_invariants() -> None:
    """Validate the registry has 5 entries, unique names, sequential sliders."""
    if len(REGISTER_PRESETS) != 5:
        raise AssertionError(f"REGISTER_PRESETS must have 5 entries; got {len(REGISTER_PRESETS)}")
    names = {p.name for p in REGISTER_PRESETS}
    if len(names) != 5:
        raise AssertionError(f"REGISTER_PRESETS names must be unique; got {names}")
    for index, preset in enumerate(REGISTER_PRESETS, start=1):
        if preset.slider != index:
            raise AssertionError(
                f"REGISTER_PRESETS[{index - 1}].slider must be {index}; got {preset.slider}"
            )
    if REGISTER_PRESETS[2].tier4_delta is not None:
        raise AssertionError(
            "REGISTER_PRESETS slider=3 (balanced) must emit tier4_delta=None per FR-007 / FR-013"
        )


_assert_registry_invariants()


def preset_for_slider(slider: int) -> RegisterPreset:
    """Look up the preset by slider value; raises ValueError if not in [1, 5].

    O(1) lookup via ``REGISTER_PRESETS[slider - 1]``. V14 budget 2
    (slider lookup P95 < 1ms) is satisfied by construction.
    """
    if slider < 1 or slider > 5:
        raise ValueError(f"slider must be in [1, 5]; got {slider}")
    return REGISTER_PRESETS[slider - 1]


def preset_for_name(name: str) -> RegisterPreset:
    """Look up the preset by canonical name; raises KeyError if unknown.

    O(N) over five entries — within V14 budget 2 by construction.
    """
    for preset in REGISTER_PRESETS:
        if preset.name == name:
            return preset
    raise KeyError(f"unknown register preset name: {name!r}")
