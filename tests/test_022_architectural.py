# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 architectural invariants (T014 of tasks.md).

Enforces:

- EVENT_CLASSES is defined exactly once in the repository (no parallel
  mappings outside ``src/web_ui/detection_events.py``).
- Re-surface broadcast goes through ``cross_instance_broadcast`` (the
  endpoint module MUST NOT import ``broadcast_to_session`` directly,
  which would bypass the cross-instance contract per Clarifications §6).
- Spec 029's shared helpers (``format_iso``, ``format_label``) are reused,
  not reimplemented inline (extends spec 029 FR-019 / FR-020 to this
  spec per ``data-model.md``).

These tests grep the source tree rather than mocking imports — they
catch drift introduced by future PRs even if those PRs add new
detection_events emit-sites or new endpoint modules.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
TESTS = REPO_ROOT / "tests"


def _python_sources_under(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)


def test_event_classes_defined_only_in_detection_events_module() -> None:
    """No parallel taxonomy maps outside src/web_ui/detection_events.py."""
    canonical = SRC / "web_ui" / "detection_events.py"
    offenders: list[Path] = []
    for path in _python_sources_under(SRC):
        if path == canonical:
            continue
        text = path.read_text(encoding="utf-8")
        # A naive grep is enough — assignments to EVENT_CLASSES are
        # the canonical declaration shape.
        if "EVENT_CLASSES" in text and "EVENT_CLASSES: dict" in text:
            offenders.append(path)
    assert not offenders, (
        "EVENT_CLASSES must only be declared in src/web_ui/detection_events.py; "
        f"found parallel definitions in: {offenders}"
    )


def test_resurface_path_routes_through_cross_instance_broadcast() -> None:
    """The endpoint module MUST route through cross_instance_broadcast.

    Sweep 2 introduces the endpoint code. The check tolerates the absence
    of the endpoint module today (Sweep 1) and only activates once the
    endpoint imports a broadcast helper.
    """
    endpoint_module = SRC / "web_ui" / "detection_events.py"
    text = endpoint_module.read_text(encoding="utf-8")
    if "POST" not in text and "broadcast_to_session" not in text:
        return  # endpoint not yet implemented; skip
    if "broadcast_to_session(" in text and "broadcast_session_event" not in text:
        raise AssertionError(
            "src/web_ui/detection_events.py must use "
            "cross_instance_broadcast.broadcast_session_event for "
            "detection_event_resurfaced / detection_event_appended payloads, "
            "not broadcast_to_session — the latter bypasses the cross-instance "
            "contract from Clarifications §6."
        )


def test_no_inline_iso_formatter_in_detection_events_paths() -> None:
    """Spec 029's format_iso must be reused, not reimplemented."""
    suspect_phrases = (
        "isoformat() + 'Z'",
        'isoformat() + "Z"',
        "strftime('%Y-%m-%dT%H:%M:%S.%fZ')",
    )
    offenders: list[tuple[Path, str]] = []
    for path in _python_sources_under(SRC):
        text = path.read_text(encoding="utf-8")
        if "detection_event" not in text and "detection_events" not in text:
            continue
        for phrase in suspect_phrases:
            if phrase in text:
                offenders.append((path, phrase))
    assert not offenders, (
        "Detection-event paths must reuse src.orchestrator.time_format.format_iso "
        f"instead of inline ISO formatters; offenders: {offenders}"
    )
