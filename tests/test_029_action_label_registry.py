# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 action-label registry tests (T012 of tasks.md).

Covers the public surface of ``src/orchestrator/audit_labels.py``:

- Registry shape: every entry has a ``label: str`` field.
- ``scrub_value`` defaults to False when the field is omitted.
- ``format_label`` returns the registered label or the
  ``[unregistered: <action>]`` fallback per FR-015 (with a WARN log on
  the unregistered path).
- ``is_scrub_value`` returns True only for entries with ``scrub_value=True``.
- The audit-label parity gate runs against the shipped frontend mirror
  AND fails on synthetic drift (regression case for FR-006).
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from src.orchestrator import audit_labels
from src.orchestrator.audit_labels import (
    LABELS,
    format_label,
    is_scrub_value,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PARITY_SCRIPT = REPO_ROOT / "scripts" / "check_audit_label_parity.py"
JS_MIRROR = REPO_ROOT / "frontend" / "audit_labels.js"


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_every_entry_has_label_string() -> None:
    assert len(LABELS) > 0
    for action, entry in LABELS.items():
        assert isinstance(entry, dict), f"{action!r} entry not a dict"
        assert "label" in entry, f"{action!r} entry missing 'label'"
        assert isinstance(entry["label"], str), f"{action!r} label is not str"
        assert entry["label"], f"{action!r} label is empty"


def test_scrub_value_default_is_false() -> None:
    """Entries omitting scrub_value behave as scrub_value=False."""
    # add_participant ships without the flag; it MUST NOT scrub.
    assert "scrub_value" not in LABELS["add_participant"]
    assert is_scrub_value("add_participant") is False


def test_scrub_value_true_for_token_actions() -> None:
    """Per research.md §9, rotate_token and revoke_token scrub values."""
    assert is_scrub_value("rotate_token") is True
    assert is_scrub_value("revoke_token") is True


def test_scrub_value_unregistered_returns_false() -> None:
    assert is_scrub_value("never_registered_xyz") is False


# ---------------------------------------------------------------------------
# format_label
# ---------------------------------------------------------------------------


def test_format_label_returns_registered_label() -> None:
    assert format_label("add_participant") == ("Facilitator added participant")


def test_format_label_unregistered_uses_fallback() -> None:
    out = format_label("totally_unknown_action")
    assert out == "[unregistered: totally_unknown_action]"


def test_format_label_unregistered_emits_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """FR-015 + research.md §10: WARN on unregistered actions."""
    with caplog.at_level(logging.WARNING, logger=audit_labels.__name__):
        format_label("drift_action_xyz")
    assert any(
        "audit_label_drift" in rec.getMessage() and "drift_action_xyz" in rec.getMessage()
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Parity gate
# ---------------------------------------------------------------------------


def test_parity_script_passes_against_shipped_mirror() -> None:
    """Happy path: backend + shipped frontend mirror agree."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(PARITY_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"parity gate failed unexpectedly:\n" f"stdout={result.stdout}\nstderr={result.stderr}"
    )


def test_parity_script_fails_on_synthetic_drift(tmp_path: Path) -> None:
    """Synthetic mirror missing a key MUST fail the gate."""
    bad_mirror = tmp_path / "audit_labels.js"
    # Mirror with only one entry; backend has many more.
    bad_mirror.write_text(
        ";(function (root, factory) {"
        '  if (typeof module === "object" && module.exports) {'
        "    module.exports = factory();"
        "  } else { root.AuditLabels = factory(); }"
        '})(typeof self !== "undefined" ? self : this, function () {'
        "  const LABELS = {"
        '    "add_participant": { label: "Facilitator added participant" },'
        "  };"
        "  function formatLabel(a) { return a; }"
        "  return { LABELS, formatLabel };"
        "});\n",
        encoding="utf-8",
    )
    # Inject the test path via env override the script supports? It
    # currently uses DEFAULT_JS_PATH; invoke via importable main()
    # instead so the path is overridable without altering the script.
    sys.path.insert(0, str(REPO_ROOT))
    import importlib

    parity_mod = importlib.import_module("scripts.check_audit_label_parity")
    rc = parity_mod.main(js_path=bad_mirror)
    assert rc == 1


def _write_mirror_with_label_override(target: Path, override_key: str, override_label: str) -> None:
    """Write a mirror that has every backend key but flips one label."""
    entries = []
    for key, entry in LABELS.items():
        label = override_label if key == override_key else entry["label"]
        entries.append(f'    "{key}": {{ label: "{label}" }},')
    body = "\n".join(entries)
    target.write_text(
        ";(function (root, factory) {"
        '  if (typeof module === "object" && module.exports) {'
        "    module.exports = factory();"
        "  } else { root.AuditLabels = factory(); }"
        '})(typeof self !== "undefined" ? self : this, function () {'
        f"  const LABELS = {{\n{body}\n  }};"
        "  function formatLabel(a) { return a; }"
        "  return { LABELS, formatLabel };"
        "});\n",
        encoding="utf-8",
    )


def test_parity_script_fails_on_label_drift(tmp_path: Path) -> None:
    """Mirror with the right keys but the wrong label MUST fail."""
    bad_mirror = tmp_path / "audit_labels.js"
    _write_mirror_with_label_override(bad_mirror, "add_participant", "WRONG LABEL")
    sys.path.insert(0, str(REPO_ROOT))
    import importlib

    parity_mod = importlib.import_module("scripts.check_audit_label_parity")
    rc = parity_mod.main(js_path=bad_mirror)
    assert rc == 1
