# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 — CAPCOM AI structured-marker parser.

A CAPCOM AI emits a turn that may carry one of two structured markers
wrapping the entire payload:

    <capcom_relay>...curated forwarding for the panel...</capcom_relay>
    <capcom_query>...question for humans on behalf of the panel...</capcom_query>

The persist path detects the marker, strips it, and writes the
message with the matching ``kind`` and ``visibility``:

  - ``capcom_relay`` → ``visibility='public'`` (panel sees the relay)
  - ``capcom_query`` → ``visibility='capcom_only'`` (only humans + CAPCOM)

Absence of a marker leaves the turn as the default ``utterance`` /
``public``. The marker MUST wrap the whole content (no surrounding
text) — partial-wrapped or embedded markers are ignored, so a CAPCOM
AI that drops the markers verbatim into ordinary prose doesn't
accidentally re-tag its own turn.

Only the active CAPCOM AI's turn is parsed for markers; panel AIs are
INV-4-rejected at write time. The caller decides who counts as CAPCOM
(via ``sessions.capcom_participant_id``).
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Anchored at start AND end (with optional whitespace) so the marker
# wraps the entire payload; this prevents embedded `<capcom_relay>...`
# strings inside ordinary prose from re-tagging the turn.
_RELAY_RE = re.compile(r"^\s*<capcom_relay>(.*)</capcom_relay>\s*$", re.DOTALL)
_QUERY_RE = re.compile(r"^\s*<capcom_query>(.*)</capcom_query>\s*$", re.DOTALL)


class CapcomMarker(NamedTuple):
    """Persistence shape: kind + visibility + stripped content."""

    kind: str
    visibility: str
    content: str


def parse_capcom_marker(content: str) -> CapcomMarker:
    """Return the CAPCOM-marker classification for ``content``.

    Default (no marker) is ``utterance`` / ``public``. The stripped
    content drops the wrapping XML so persisted rows carry only the
    payload — the structural attribution rides on the ``kind`` field.
    """
    m = _RELAY_RE.match(content)
    if m is not None:
        return CapcomMarker(kind="capcom_relay", visibility="public", content=m.group(1).strip())
    m = _QUERY_RE.match(content)
    if m is not None:
        return CapcomMarker(
            kind="capcom_query",
            visibility="capcom_only",
            content=m.group(1).strip(),
        )
    return CapcomMarker(kind="utterance", visibility="public", content=content)
