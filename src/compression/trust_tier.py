# SPDX-License-Identifier: AGPL-3.0-or-later

"""Trust-tier inheritance + tier-1 refusal — spec 026 FR-011, FR-014.

Per Session 2026-05-11 §3, a compressed segment inherits the MIN tier
of its input segments (most-restrictive wins). Tier-1 (`system`)
content is NEVER compressed per FR-014 — non-NoOp compressors call
`refuse_tier_one(tier)` at entry to enforce.
"""

from __future__ import annotations

# High-to-low ordering. MIN-tier picks the entry with the largest index.
TIER_ORDER: tuple[str, ...] = (
    "system",
    "facilitator",
    "participant_supplied",
)


class TierOneRefusalError(Exception):
    """Raised when a non-NoOp compressor is invoked on tier-1 content.

    The CompressorService catches this and surfaces it as a
    `routing_log.reason='compression_pipeline_error'` per FR-020;
    the dispatch falls through to un-compressed payload.
    """


def resolve_min_tier(source_tiers: list[str]) -> str:
    """Return the most-restrictive (lowest-trust) tier from `source_tiers`.

    Per Session 2026-05-11 §3 MIN-tier inheritance. Mixed-tier source
    compresses to the lower tier; the XML boundary marker records the
    lower tier per FR-012.
    """
    if not source_tiers:
        raise ValueError("source_tiers must be non-empty")
    for tier in source_tiers:
        if tier not in TIER_ORDER:
            raise ValueError(f"unknown trust tier: {tier!r}")
    return max(source_tiers, key=lambda t: TIER_ORDER.index(t))


def refuse_tier_one(trust_tier: str) -> None:
    """Raise TierOneRefusalError if `trust_tier == 'system'`.

    Non-NoOp compressors call this at entry to enforce FR-014. NoOp
    is exempt — it produces byte-identical output and inserts no
    compression artefact.
    """
    if trust_tier == "system":
        raise TierOneRefusalError(
            "tier-1 content (system prompt + tool defs) MUST NOT be compressed; " "spec 026 FR-014"
        )
