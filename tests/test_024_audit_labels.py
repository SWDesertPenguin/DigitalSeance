# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 024 audit-label registry: five new entries.

Backs T003 + clarify session 2026-05-12 §12. Each new action MUST be
registered on both the backend (src/orchestrator/audit_labels.py) and
the frontend (frontend/audit_labels.js); the parity gate enforces
equality.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.orchestrator.audit_labels import LABELS, format_label, is_scrub_value

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_LABELS = REPO_ROOT / "frontend" / "audit_labels.js"

EXPECTED_NEW_KEYS = (
    "facilitator_note_created",
    "facilitator_note_updated",
    "facilitator_note_deleted",
    "facilitator_promoted_note",
    "facilitator_note_purged_retention",
)


def test_all_five_new_actions_registered_backend() -> None:
    for key in EXPECTED_NEW_KEYS:
        assert key in LABELS, f"missing backend label: {key}"


def test_format_label_returns_english_strings() -> None:
    seen = set()
    for key in EXPECTED_NEW_KEYS:
        label = format_label(key)
        assert isinstance(label, str)
        assert "facilitator" in label.lower() or "scratch" in label.lower()
        assert label not in seen, f"duplicate label: {label}"
        seen.add(label)


def test_no_scrub_value_on_facilitator_actions() -> None:
    """Notes are ScrubFilter-processed at write time; registry-level scrub
    would double-scrub and hide the historical content from the audit panel."""
    for key in EXPECTED_NEW_KEYS:
        assert is_scrub_value(key) is False


def test_frontend_mirror_carries_all_five_keys() -> None:
    """Spec 029 contracts/shared-module-contracts.md §1 parity surface."""
    text = FRONTEND_LABELS.read_text(encoding="utf-8")
    for key in EXPECTED_NEW_KEYS:
        pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*\{{[^}}]*\}}')
        assert pattern.search(text) is not None, f"missing frontend mirror: {key}"


def test_backend_and_frontend_label_strings_match() -> None:
    """If labels drift between backend / frontend, the parity gate fails the
    build — this test is a faster local check."""
    text = FRONTEND_LABELS.read_text(encoding="utf-8")
    for key in EXPECTED_NEW_KEYS:
        backend_label = LABELS[key]["label"]
        # Extract the frontend label string for this key.
        pattern = re.compile(
            rf'"{re.escape(key)}"\s*:\s*\{{\s*label:\s*"([^"]+)"',
        )
        match = pattern.search(text)
        assert match is not None, f"could not locate frontend label for {key}"
        assert match.group(1) == backend_label, (
            f"label drift for {key}: backend={backend_label!r} " f"frontend={match.group(1)!r}"
        )


def test_json_serialisable_for_audit_panel_payload() -> None:
    """Each entry MUST round-trip through json.dumps so the audit panel
    payload (spec 029 FR-001) survives the wire."""
    for key in EXPECTED_NEW_KEYS:
        entry = LABELS[key]
        roundtrip = json.loads(json.dumps(entry))
        assert roundtrip["label"] == entry["label"]
