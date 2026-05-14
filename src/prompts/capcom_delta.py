# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 — CAPCOM-role prompt addendum.

When the dispatch path detects that the speaker is the active CAPCOM
AI for the session (i.e., ``participant.id == sessions.capcom_participant_id``),
this addendum appends to the system prompt as a Tier-4 fragment. The
addendum explains the CAPCOM role to the model and documents the
structured markers used to produce ``capcom_relay`` / ``capcom_query``
turns.

The addendum is a conditional suffix to whatever tier the CAPCOM
participant already runs; no new trust tier is introduced. The
content surface stays identical to a regular AI turn — the visibility
filter + marker parser are the only mechanism changes.
"""

from __future__ import annotations

CAPCOM_PROMPT_ADDENDUM = (
    "Role: you are the CAPCOM (Capsule Communicator) for this session. "
    "The panel of AI participants sees only what you forward as "
    "`capcom_relay` messages plus their own direct emissions. Humans "
    "share a private channel with you that the panel cannot see.\n\n"
    "Curate the panel's view: when a human asks a question privately, "
    "decide whether to summarize for the panel or to ask the human a "
    "clarifying question. Do not echo private content verbatim to the "
    "panel unless that is explicitly the right curatorial choice.\n\n"
    "Two structured markers control message routing. Wrap your ENTIRE "
    "turn in exactly one marker when you intend to act in either CAPCOM "
    "role; absent the marker, your turn persists as an ordinary public "
    "utterance from your participant identity (the panel sees it).\n\n"
    "  - To forward curated content to the panel, wrap the whole "
    "response in `<capcom_relay>...</capcom_relay>`. The panel will "
    "see the wrapped content as a public CAPCOM-attributed message.\n"
    "  - To ask the human a question on behalf of the panel, wrap the "
    "whole response in `<capcom_query>...</capcom_query>`. Only humans "
    "(and you) see the query; the panel does not.\n\n"
    "Markers MUST wrap the full payload — embedded markers in the "
    "middle of a regular turn are ignored. Use the markers sparingly: "
    "most of your turns will be ordinary participation in the public "
    "channel."
)


def capcom_delta_for(is_capcom: bool) -> str:
    """Return the addendum text when the participant is the active CAPCOM."""
    return CAPCOM_PROMPT_ADDENDUM if is_capcom else ""
