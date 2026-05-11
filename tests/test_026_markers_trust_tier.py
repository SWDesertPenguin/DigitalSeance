# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 trust-tier + XML boundary marker tests (T021).

Covers research.md §7 — MIN-tier inheritance per Session 2026-05-11 §3,
tier-1 refusal per FR-014, XML boundary marker assembly per FR-012.
"""

from __future__ import annotations

import pytest

from src.compression.markers import wrap
from src.compression.trust_tier import (
    TIER_ORDER,
    TierOneRefusalError,
    refuse_tier_one,
    resolve_min_tier,
)

# ---------------------------------------------------------------------------
# resolve_min_tier — MIN-tier inheritance (Session 2026-05-11 §3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tiers", "expected"),
    [
        (["system"], "system"),
        (["facilitator"], "facilitator"),
        (["participant_supplied"], "participant_supplied"),
        (["system", "facilitator"], "facilitator"),
        (["system", "participant_supplied"], "participant_supplied"),
        (["facilitator", "participant_supplied"], "participant_supplied"),
        (
            ["system", "facilitator", "participant_supplied"],
            "participant_supplied",
        ),
    ],
)
def test_min_tier_picks_lowest_trust(tiers: list[str], expected: str) -> None:
    assert resolve_min_tier(tiers) == expected


def test_min_tier_rejects_empty() -> None:
    with pytest.raises(ValueError):
        resolve_min_tier([])


def test_min_tier_rejects_unknown_tier() -> None:
    with pytest.raises(ValueError):
        resolve_min_tier(["participant_supplied", "bogus_tier"])


def test_tier_order_is_high_to_low() -> None:
    """The TIER_ORDER tuple encodes the high-to-low trust ordering."""
    assert TIER_ORDER == ("system", "facilitator", "participant_supplied")


# ---------------------------------------------------------------------------
# refuse_tier_one — FR-014
# ---------------------------------------------------------------------------


def test_refuse_tier_one_raises_on_system_tier() -> None:
    with pytest.raises(TierOneRefusalError):
        refuse_tier_one("system")


@pytest.mark.parametrize("tier", ["facilitator", "participant_supplied"])
def test_refuse_tier_one_passes_on_non_system(tier: str) -> None:
    # Returns None implicitly; raises nothing.
    assert refuse_tier_one(tier) is None


# ---------------------------------------------------------------------------
# wrap — XML boundary marker assembly (FR-012)
# ---------------------------------------------------------------------------


def test_wrap_produces_expected_xml_shape() -> None:
    result = wrap(
        "compressed body here",
        source_tier="participant_supplied",
        compressor_id="llmlingua2_mbert",
        compressor_version="1.0",
    )
    assert result.startswith("<compressed")
    assert result.endswith("</compressed>")
    assert 'source-tier="participant_supplied"' in result
    assert 'compressor="llmlingua2_mbert"' in result
    assert 'version="1.0"' in result
    assert ">compressed body here<" in result


def test_wrap_escapes_attribute_values() -> None:
    """Attribute values are XML-quoted via quoteattr — embedded quotes survive."""
    result = wrap(
        "body",
        source_tier='tier"with"quotes',
        compressor_id="cid",
        compressor_version="1",
    )
    # quoteattr switches to single quotes when value contains double quotes;
    # the resulting markup must still be well-formed.
    assert "&quot;" in result or "'tier\"with\"quotes'" in result


def test_wrap_does_not_escape_body() -> None:
    """Body content passes through; compressor owns its own sanitisation."""
    body = "raw <tag> content with & chars"
    result = wrap(
        body,
        source_tier="participant_supplied",
        compressor_id="noop",
        compressor_version="1",
    )
    assert body in result
