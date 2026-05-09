#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Action-label parity CI gate (spec 029 FR-006 / research.md §4).

Imports ``src.orchestrator.audit_labels`` and parses the literal
``LABELS = {...}`` block in ``frontend/audit_labels.js`` with a small
state-machine parser. Compares key sets and ``label`` strings; fails with
a structured error naming the offending key on drift.

The frontend mirror MUST contain every backend key with a matching
``label`` string. ``scrub_value`` is backend-only (per FR-006 design) and
is NOT parity-checked. Any frontend-only keys also fail the build.

Usage:
    python scripts/check_audit_label_parity.py

Exit codes:
    0 = parity
    1 = drift (with diff written to stderr)

The JS parser deliberately rejects forms outside the established UMD
shape (comments, computed keys, spread). When a future spec needs richer
JS-side declarations, add a real JS parser dependency or migrate the
mirror to a JSON manifest. Kept under 100 lines per research.md §4.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JS_PATH = REPO_ROOT / "frontend" / "audit_labels.js"

# Allow imports from src.* by prepending the repo root.
sys.path.insert(0, str(REPO_ROOT))

from src.orchestrator import audit_labels  # noqa: E402,I001


_LABELS_BLOCK_RE = re.compile(
    r"const\s+LABELS\s*=\s*\{(?P<body>.*?)\};",
    re.DOTALL,
)
# One entry per line:
#   "action": { label: "..." [, ...] },
# We intentionally support only the shape the registry uses. Everything
# else trips the strict-mode error.
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


def _extract_labels_block(js_text: str) -> str:
    """Locate the ``const LABELS = {...};`` literal body or raise."""
    match = _LABELS_BLOCK_RE.search(js_text)
    if not match:
        raise ValueError(
            "frontend/audit_labels.js: could not locate `const LABELS = {...};`",
        )
    body = match.group("body")
    if "//" in body or "/*" in body:
        raise ValueError(
            "frontend/audit_labels.js: comments inside the LABELS block are "
            "not supported by the parity parser. Move comments outside.",
        )
    return body


def parse_js_labels(js_text: str) -> dict[str, str]:
    """Extract ``{key: label}`` from the frontend ``LABELS`` literal."""
    body = _extract_labels_block(js_text)
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
                f"frontend/audit_labels.js: unparseable entry near {pos}: {tail!r}",
            )
        key = m.group("key")
        if key in out:
            raise ValueError(f"frontend/audit_labels.js: duplicate key {key!r}")
        out[key] = m.group("label").replace('\\"', '"')
        pos = m.end()
    return out


def diff_registries(
    py_labels: dict[str, str],
    js_labels: dict[str, str],
) -> list[str]:
    """Return a list of human-readable drift descriptions (empty = parity)."""
    errors: list[str] = []
    py_keys = set(py_labels)
    js_keys = set(js_labels)
    for key in sorted(py_keys - js_keys):
        errors.append(
            f"  backend has key {key!r} but frontend mirror does not",
        )
    for key in sorted(js_keys - py_keys):
        errors.append(
            f"  frontend has key {key!r} but backend registry does not",
        )
    for key in sorted(py_keys & js_keys):
        if py_labels[key] != js_labels[key]:
            errors.append(
                f"  label drift on {key!r}: "
                f"backend={py_labels[key]!r} frontend={js_labels[key]!r}",
            )
    return errors


def main(js_path: Path = DEFAULT_JS_PATH) -> int:
    py_labels = {key: str(entry["label"]) for key, entry in audit_labels.LABELS.items()}
    js_text = js_path.read_text(encoding="utf-8")
    js_labels = parse_js_labels(js_text)
    errors = diff_registries(py_labels, js_labels)
    if errors:
        sys.stderr.write(
            "audit-label parity drift detected "
            "(spec 029 FR-006; shared-module-contracts.md §5):\n",
        )
        for line in errors:
            sys.stderr.write(line + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
