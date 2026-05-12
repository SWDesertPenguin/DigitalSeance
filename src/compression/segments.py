# SPDX-License-Identifier: AGPL-3.0-or-later

"""CompressedSegment + Compressor Protocol — spec 026 FR-006.

The `CompressedSegment` dataclass is the output type of every
`Compressor.compress(...)` call. The `Compressor` Protocol fixes the
shape every layer-N implementation must honour. The dispatch path
consumes only these two types — concrete compressor classes stay
internal to the compression package per FR-023.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompressedSegment:
    """Output of `Compressor.compress(...)`.

    NoOp dispatches produce a segment whose `output_text` is byte-identical
    to the input (SC-006) and whose `boundary_marker` is None. Real
    compressors set a boundary marker per FR-012.
    """

    output_text: str
    output_tokens: int
    trust_tier: str
    boundary_marker: str | None
    compressor_id: str
    compressor_version: str


class Compressor(Protocol):
    """Per-layer compressor interface.

    Implementations expose two class-level identifiers and one method.
    The dispatcher reads `COMPRESSOR_ID` and `COMPRESSOR_VERSION` for
    the registry + telemetry; the body lives in `compress(...)`.
    """

    COMPRESSOR_ID: str
    COMPRESSOR_VERSION: str

    def compress(
        self,
        payload: str,
        target_budget: int,
        trust_tier: str,
    ) -> CompressedSegment:
        """Compress `payload` to fit roughly within `target_budget` tokens.

        Implementations MAY ignore `target_budget` (NoOp) or treat it
        as advisory. `trust_tier` is one of system / facilitator /
        participant_supplied. Tier-1 (`system`) refuse-to-compress per
        FR-014 is enforced by non-NoOp compressors at entry.
        """
        ...
