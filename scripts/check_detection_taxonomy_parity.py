#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Detection-event taxonomy parity CI gate (spec 022 research.md §16).

Imports ``src.web_ui.detection_events`` and parses the literal
``EVENT_CLASSES = {...}`` block in ``frontend/detection_event_taxonomy.js``
with a small state-machine parser. Compares key sets and ``label`` strings;
fails with a structured error naming the offending key on drift.

The frontend mirror MUST contain every backend key with a matching
``label`` string. Any frontend-only keys also fail the build.

Mirrors ``scripts/check_audit_label_parity.py`` in shape; both gates are
required-passing in CI per the Constitution §V19 architectural pattern.

Usage:
    python scripts/check_detection_taxonomy_parity.py

Exit codes:
    0 = parity
    1 = drift (with diff written to stderr)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JS_PATH = REPO_ROOT / "frontend" / "detection_event_taxonomy.js"

sys.path.insert(0, str(REPO_ROOT))

from src.web_ui import detection_events  # noqa: E402,I001


_BLOCK_RE = re.compile(
    r"const\s+EVENT_CLASSES\s*=\s*\{(?P<body>.*?)\};",
    re.DOTALL,
)
_ENTRY_RE = re.compile(
    r"""
    \s*
    "(?P<key>[A-Za-z0-9_]+)"
    \s*:\s*
    \{\s*label\s*:\s*"(?P<label>(?:[^"\\]|\\.)*)"\s*\}
    \s*,?\s*
    """,
    re.VERBOSE,
)


def _extract_block(js_text: str) -> str:
    """Locate the ``const EVENT_CLASSES = {...};`` literal body or raise."""
    match = _BLOCK_RE.search(js_text)
    if not match:
        raise ValueError(
            "frontend/detection_event_taxonomy.js: could not locate "
            "`const EVENT_CLASSES = {...};`",
        )
    body = match.group("body")
    if "//" in body or "/*" in body:
        raise ValueError(
            "frontend/detection_event_taxonomy.js: comments inside the "
            "EVENT_CLASSES block are not supported by the parity parser. "
            "Move comments outside.",
        )
    return body


def parse_js_event_classes(js_text: str) -> dict[str, str]:
    """Extract ``{key: label}`` from the frontend ``EVENT_CLASSES`` literal."""
    body = _extract_block(js_text)
    out: dict[str, str] = {}
    pos = 0
    while pos < len(body):
        while pos < len(body) and body[pos] in " \t\r\n":
            pos += 1
        if pos >= len(body):
            break
        m = _ENTRY_RE.match(body, pos)
        if not m:
            tail = body[pos : pos + 80].replace("\n", "\\n")
            raise ValueError(
                "frontend/detection_event_taxonomy.js: unparseable entry " f"near {pos}: {tail!r}",
            )
        key = m.group("key")
        if key in out:
            raise ValueError(
                f"frontend/detection_event_taxonomy.js: duplicate key {key!r}",
            )
        out[key] = m.group("label").replace('\\"', '"')
        pos = m.end()
    return out


def diff_registries(
    py_classes: dict[str, str],
    js_classes: dict[str, str],
) -> list[str]:
    """Return human-readable drift descriptions (empty = parity)."""
    errors: list[str] = []
    py_keys = set(py_classes)
    js_keys = set(js_classes)
    for key in sorted(py_keys - js_keys):
        errors.append(
            f"  backend has key {key!r} but frontend mirror does not",
        )
    for key in sorted(js_keys - py_keys):
        errors.append(
            f"  frontend has key {key!r} but backend registry does not",
        )
    for key in sorted(py_keys & js_keys):
        if py_classes[key] != js_classes[key]:
            errors.append(
                f"  label drift on {key!r}: "
                f"backend={py_classes[key]!r} frontend={js_classes[key]!r}",
            )
    return errors


def main(js_path: Path = DEFAULT_JS_PATH) -> int:
    py_classes = {key: str(entry["label"]) for key, entry in detection_events.EVENT_CLASSES.items()}
    js_text = js_path.read_text(encoding="utf-8")
    js_classes = parse_js_event_classes(js_text)
    errors = diff_registries(py_classes, js_classes)
    if errors:
        sys.stderr.write(
            "detection-event taxonomy parity drift detected " "(spec 022 research.md §16):\n",
        )
        for line in errors:
            sys.stderr.write(line + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
