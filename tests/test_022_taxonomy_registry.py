# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 taxonomy-registry unit tests (T012 of tasks.md).

Covers:

- EVENT_CLASSES shape (every key has a ``label`` string).
- ``format_class_label`` happy path and fallback marker.
- Parity-gate failure-mode against a synthetic-drift JS module.

Test fixtures keep the parity-gate exercise off the real frontend
mirror so the gate's own CI passes regardless of test execution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_detection_taxonomy_parity as parity
from src.web_ui import detection_events


def test_event_classes_has_five_entries() -> None:
    """Clarifications §3 + §8 fixed five-class taxonomy."""
    assert set(detection_events.EVENT_CLASSES) == {
        "ai_question_opened",
        "ai_exit_requested",
        "density_anomaly",
        "mode_recommendation",
        "mode_change",
    }


def test_every_entry_has_label_string() -> None:
    for key, entry in detection_events.EVENT_CLASSES.items():
        assert "label" in entry, f"{key} missing label field"
        assert isinstance(entry["label"], str), f"{key} label not a string"
        assert entry["label"], f"{key} label is empty"


def test_format_class_label_happy_path() -> None:
    assert detection_events.format_class_label("density_anomaly") == "Density anomaly"


def test_format_class_label_fallback() -> None:
    """Unregistered keys render with the [unregistered: <key>] marker."""
    assert (
        detection_events.format_class_label("future_unregistered_class")
        == "[unregistered: future_unregistered_class]"
    )


def test_format_class_label_logs_warn_on_unregistered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="src.web_ui.detection_events")
    detection_events.format_class_label("future_unregistered_class")
    messages = [r.message for r in caplog.records]
    assert any("unregistered_class_key" in m for m in messages)


# ---------------------------------------------------------------------------
# Parity-gate failure-mode coverage
# ---------------------------------------------------------------------------


def test_parity_gate_detects_missing_frontend_key(tmp_path: Path) -> None:
    """Backend key absent from frontend → parity gate exits non-zero."""
    drifted = tmp_path / "drifted.js"
    drifted.write_text(
        # Intentionally omits "density_anomaly".
        """const EVENT_CLASSES = {
            "ai_question_opened": { label: "AI question opened" },
            "ai_exit_requested": { label: "AI exit requested" },
            "mode_recommendation": { label: "Mode recommendation" },
            "mode_change": { label: "Mode change" },
        };""",
        encoding="utf-8",
    )
    exit_code = parity.main(js_path=drifted)
    assert exit_code == 1


def test_parity_gate_detects_label_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Backend label != frontend label for the same key → parity gate fails."""
    drifted = tmp_path / "drifted.js"
    drifted.write_text(
        """const EVENT_CLASSES = {
            "ai_question_opened": { label: "AI question opened" },
            "ai_exit_requested": { label: "AI exit requested" },
            "density_anomaly": { label: "DIFFERENT LABEL" },
            "mode_recommendation": { label: "Mode recommendation" },
            "mode_change": { label: "Mode change" },
        };""",
        encoding="utf-8",
    )
    exit_code = parity.main(js_path=drifted)
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "density_anomaly" in err


def test_parity_gate_passes_on_clean_default() -> None:
    """The real frontend mirror MUST parity-check clean."""
    assert parity.main() == 0
