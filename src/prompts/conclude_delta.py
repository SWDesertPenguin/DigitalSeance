"""Spec 025 conclude-phase Tier 4 prompt delta.

Per spec 025 research.md §5 and data-model.md §ConcludeDelta, this module
holds the hardcoded conclude-delta text and the injection helper used by
the prompt assembler when the loop's current phase is `conclude`.

Composition order at Tier 4 (per research.md §4 forward-compatible
ordering): `custom_prompt` → spec 021 register-slider delta (when 021
ships) → conclude delta. All additive; the conclude delta MUST NOT
replace the participant's tier text or custom_prompt.
"""

from __future__ import annotations
