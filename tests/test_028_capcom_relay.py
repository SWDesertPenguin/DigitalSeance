# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR-012/§FR-013 — capcom_relay / capcom_query marker parser."""

from __future__ import annotations

from src.orchestrator.capcom_relay import parse_capcom_marker


def test_plain_utterance_passes_through():
    out = parse_capcom_marker("just a regular turn")
    assert out.kind == "utterance"
    assert out.visibility == "public"
    assert out.content == "just a regular turn"


def test_capcom_relay_marker_strips_wrapper():
    out = parse_capcom_marker("<capcom_relay>panel needs this summary</capcom_relay>")
    assert out.kind == "capcom_relay"
    assert out.visibility == "public"
    assert out.content == "panel needs this summary"


def test_capcom_query_marker_strips_wrapper():
    out = parse_capcom_marker("<capcom_query>can you clarify X?</capcom_query>")
    assert out.kind == "capcom_query"
    assert out.visibility == "capcom_only"
    assert out.content == "can you clarify X?"


def test_marker_wraps_whole_payload_only():
    """A marker embedded inside ordinary prose MUST NOT re-tag the turn."""
    out = parse_capcom_marker(
        "the panel asked me to relay: <capcom_relay>something</capcom_relay> okay?"
    )
    assert out.kind == "utterance"
    assert out.visibility == "public"


def test_marker_tolerates_surrounding_whitespace():
    out = parse_capcom_marker("  <capcom_relay>hi</capcom_relay>\n")
    assert out.kind == "capcom_relay"
    assert out.content == "hi"


def test_marker_handles_multiline_payload():
    payload = "<capcom_relay>line 1\nline 2\nline 3</capcom_relay>"
    out = parse_capcom_marker(payload)
    assert out.kind == "capcom_relay"
    assert out.content == "line 1\nline 2\nline 3"
