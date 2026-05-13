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

    Sweep 3 introduces the POST .../resurface handler. The check only
    activates once the endpoint module references broadcast helpers.
    """
    endpoint_module = SRC / "participant_api" / "tools" / "detection_events.py"
    if not endpoint_module.exists():
        return
    text = endpoint_module.read_text(encoding="utf-8")
    if "POST" not in text and "broadcast_to_session" not in text:
        return
    if "broadcast_to_session(" in text and "broadcast_session_event" not in text:
        raise AssertionError(
            "src/participant_api/tools/detection_events.py must use "
            "cross_instance_broadcast.broadcast_session_event for "
            "detection_event_resurfaced / detection_event_appended payloads, "
            "not broadcast_to_session — the latter bypasses the cross-instance "
            "contract from Clarifications §6."
        )


def test_detection_event_emit_sites_reuse_shared_dual_write_helper() -> None:
    """The four emit sites MUST delegate to persist_and_broadcast_detection_event.

    Per FR-017 + data-model.md "Dual-write contract": each detector emit
    site builds a DetectionEventDraft and hands off to the shared helper
    in src/web_ui/events.py. A new emit site that calls
    insert_detection_event directly (bypassing the broadcast half) would
    silently break the live-update WS contract.
    """
    # Only the repo (definition) and the shared events helper should
    # import insert_detection_event directly. All other emit sites must
    # go through persist_and_broadcast_detection_event so the dual-write
    # contract (INSERT + WS broadcast) stays atomic.
    expected_callers = {
        "src/repositories/detection_event_repo.py",  # definition
        "src/web_ui/events.py",  # shared helper
    }
    actual_callers: set[str] = set()
    for path in _python_sources_under(SRC):
        text = path.read_text(encoding="utf-8")
        if "insert_detection_event" in text:
            rel = path.relative_to(REPO_ROOT).as_posix()
            actual_callers.add(rel)
    extras = actual_callers - expected_callers
    assert not extras, (
        "Unexpected modules import insert_detection_event directly; "
        "any new emit site MUST route through "
        "src.web_ui.events.persist_and_broadcast_detection_event: "
        f"unexpected callers = {extras}"
    )


def test_detection_event_envelope_builders_paired_with_cross_instance_broadcast() -> None:
    """Modules that build detection_event_* envelopes MUST also import
    broadcast_session_event from cross_instance_broadcast.

    The cross_instance_broadcast layer handles same-instance + LISTEN/NOTIFY
    fan-out per Clarifications §6. Any module emitting these envelopes
    must use the cross-instance helper rather than the legacy
    per-process broadcast_to_session helper that doesn't carry the
    LISTEN/NOTIFY hop.
    """
    builders = ("detection_event_appended_event", "detection_event_resurfaced_event")
    offenders: list[str] = []
    for path in _python_sources_under(SRC):
        text = path.read_text(encoding="utf-8")
        builds_envelope = any(b in text for b in builders)
        if not builds_envelope:
            continue
        if "broadcast_session_event" not in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        "Modules building detection_event_* envelopes must also import "
        "cross_instance_broadcast.broadcast_session_event: "
        f"offenders = {offenders}"
    )


def test_spa_refetches_detection_history_on_reconnect_and_window_focus() -> None:
    """T054: the SPA MUST refetch the page on WS reconnect AND visibility return.

    FR-009 (best-effort cross-instance push) substitutes at-least-once
    delivery with eventual consistency via REST refetch. The SPA hooks
    on two triggers: (a) wsState transition non-open → open, and
    (b) document.visibilitychange after the inactivity threshold. The
    test greps frontend/app.jsx for the wiring rather than spinning up
    a JS runtime — if the hooks regress, the assertion fires.
    """
    spa_path = REPO_ROOT / "frontend" / "app.jsx"
    text = spa_path.read_text(encoding="utf-8")
    # WS reconnect refetch: prevWsStateRef + transition guard + fetch.
    assert (
        "prevWsStateRef" in text
    ), "frontend/app.jsx MUST track previous wsState to detect reconnect transitions"
    assert (
        'prev !== "open" && wsState === "open"' in text
        or "prev !== 'open' && wsState === 'open'" in text
    ), "frontend/app.jsx MUST refetch the detection-history panel on WS reconnect"
    # Visibility-change refetch: visibilitychange listener with inactivity gate.
    assert "visibilitychange" in text, (
        "frontend/app.jsx MUST wire a visibilitychange listener for the "
        "detection-history refetch trigger"
    )
    assert (
        "DETECTION_HISTORY_INACTIVITY_REFETCH_MS" in text
    ), "frontend/app.jsx MUST define an inactivity threshold for refetch"


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
