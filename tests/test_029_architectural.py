# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 FR-020 architectural enforcement.

Walks ``src/orchestrator/`` (Python) and ``frontend/`` (JS) and fails the
build when any module other than the canonical action-label registry
declares a module-level mapping whose keys overlap with the registered
audit action strings.

Per spec 029 FR-020 + ``contracts/shared-module-contracts.md`` §6: the
backend ``src/orchestrator/audit_labels.py`` and the frontend
``frontend/audit_labels.js`` are the ONLY modules permitted to declare
audit-action-to-label mappings. Any future spec that tries to ship a
parallel mapping hits this gate.

Detection strategy:

- Python: AST-walk the file, look for module-level ``ast.Assign`` /
  ``ast.AnnAssign`` whose RHS is a ``dict`` literal; flag if the key
  set overlaps the registered audit action strings.
- JS: lightweight regex on object-literal keys (the JS module pattern
  used in this repo writes literals at module scope, never builds them
  dynamically). Catches the violation that matters: someone shipping a
  ``const FOO = {add_participant: ..., remove_participant: ...}``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.orchestrator.audit_labels import LABELS

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_SCAN_ROOT = REPO_ROOT / "src" / "orchestrator"
JS_SCAN_ROOT = REPO_ROOT / "frontend"
ALLOWED_PY = {PY_SCAN_ROOT / "audit_labels.py"}
ALLOWED_JS = {JS_SCAN_ROOT / "audit_labels.js"}

ACTION_KEYS = frozenset(LABELS.keys())
# Treat overlap of two or more registered keys as a violation. A single
# coincidental key (e.g. someone using ``"add_participant"`` as a string
# literal in a single-element dict) is not enough signal to fail; the
# pattern that matters is a *table* of audit-action mappings.
OVERLAP_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Python AST walker
# ---------------------------------------------------------------------------


def _module_level_dict_target(node: ast.AST) -> tuple[str | None, ast.AST | None]:
    """Return (name, value) when node is a module-level name = dict-literal."""

    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id, node.value
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
    ):
        return node.target.id, node.value
    return None, None


def _string_keys_of_dict(value: ast.AST) -> set[str]:
    """Return the set of string-constant keys of a dict literal node."""

    if not isinstance(value, ast.Dict):
        return set()
    return {
        key.value
        for key in value.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _module_level_dict_keys(tree: ast.Module) -> list[tuple[str, set[str]]]:
    """Return ``(name, keys)`` tuples for every module-level dict literal."""

    out: list[tuple[str, set[str]]] = []
    for node in tree.body:
        target_name, value = _module_level_dict_target(node)
        if target_name is None or value is None:
            continue
        keys = _string_keys_of_dict(value)
        out.append((target_name, keys))
    return out


def _scan_python() -> list[tuple[Path, str, set[str]]]:
    """Return ``(path, dict_name, overlapping_keys)`` triples for offenders."""

    offenders: list[tuple[Path, str, set[str]]] = []
    for py in PY_SCAN_ROOT.rglob("*.py"):
        if py in ALLOWED_PY:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for name, keys in _module_level_dict_keys(tree):
            overlap = keys & ACTION_KEYS
            if len(overlap) >= OVERLAP_THRESHOLD:
                offenders.append((py, name, overlap))
    return offenders


# ---------------------------------------------------------------------------
# JS regex walker
# ---------------------------------------------------------------------------


# Match an object-literal opener (``= {`` or ``: {``) followed by string-
# quoted keys: ``"foo":`` / ``'foo':``. Identifier-style keys (``foo:``)
# can also be audit action strings, so capture both.
_JS_OBJECT_LITERAL = re.compile(r"=\s*\{([^}]{0,4096})\}", re.DOTALL)
_JS_STRING_KEY = re.compile(r'["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*:')
_JS_BARE_KEY = re.compile(r"(?:^|[\{,\s])([A-Za-z_][A-Za-z0-9_]*)\s*:")


def _scan_javascript() -> list[tuple[Path, set[str]]]:
    """Return ``(path, overlapping_keys)`` tuples for offending JS files."""

    offenders: list[tuple[Path, set[str]]] = []
    for js in JS_SCAN_ROOT.rglob("*.js"):
        if js in ALLOWED_JS:
            continue
        text = js.read_text(encoding="utf-8")
        worst_overlap: set[str] = set()
        for body_match in _JS_OBJECT_LITERAL.finditer(text):
            body = body_match.group(1)
            keys = set(_JS_STRING_KEY.findall(body)) | set(_JS_BARE_KEY.findall(body))
            overlap = keys & ACTION_KEYS
            if len(overlap) > len(worst_overlap):
                worst_overlap = overlap
        if len(worst_overlap) >= OVERLAP_THRESHOLD:
            offenders.append((js, worst_overlap))
    return offenders


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_python_module_declares_parallel_action_label_mapping() -> None:
    """FR-020: only ``src/orchestrator/audit_labels.py`` may declare LABELS."""

    offenders = _scan_python()
    assert offenders == [], (
        "FR-020 violation — module(s) other than src/orchestrator/audit_labels.py "
        "declare a module-level dict whose keys overlap the audit action registry: "
        + "; ".join(
            f"{path.relative_to(REPO_ROOT)}::{name} (overlapping keys: " f"{sorted(overlap)})"
            for path, name, overlap in offenders
        )
    )


def test_no_js_module_declares_parallel_action_label_mapping() -> None:
    """FR-020: only ``frontend/audit_labels.js`` may declare LABELS."""

    offenders = _scan_javascript()
    assert offenders == [], (
        "FR-020 violation — frontend module(s) other than frontend/audit_labels.js "
        "declare an object literal whose keys overlap the audit action registry: "
        + "; ".join(
            f"{path.relative_to(REPO_ROOT)} (overlapping keys: {sorted(overlap)})"
            for path, overlap in offenders
        )
    )


def test_canonical_python_module_passes_overlap_threshold() -> None:
    """Sanity: the registered module DOES contain >= OVERLAP_THRESHOLD keys."""

    text = (PY_SCAN_ROOT / "audit_labels.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    found = False
    for name, keys in _module_level_dict_keys(tree):
        if name == "LABELS" and len(keys & ACTION_KEYS) >= OVERLAP_THRESHOLD:
            found = True
            break
    assert found, "audit_labels.LABELS must contain audit action keys"


def test_synthetic_violation_is_caught(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop a violating module under a temp orchestrator path; assert it trips."""

    fake_root = tmp_path / "src" / "orchestrator"
    fake_root.mkdir(parents=True)
    # Mirror the canonical registry so the "allowed" path is excluded.
    (fake_root / "audit_labels.py").write_text(
        "LABELS = {\n" + "\n".join(f"    {k!r}: {{'label': 'x'}}," for k in LABELS) + "\n}\n",
        encoding="utf-8",
    )
    # Drop a violator that mirrors several action keys in a parallel dict.
    sample_keys = list(LABELS)[: OVERLAP_THRESHOLD + 1]
    (fake_root / "rogue_registry.py").write_text(
        "BAD = {\n" + "\n".join(f"    {k!r}: 'rogue'," for k in sample_keys) + "\n}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("tests.test_029_architectural.PY_SCAN_ROOT", fake_root)
    monkeypatch.setattr(
        "tests.test_029_architectural.ALLOWED_PY",
        {fake_root / "audit_labels.py"},
    )

    offenders = _scan_python()
    assert offenders, "synthetic violation MUST be detected"
    paths = [str(p) for p, _, _ in offenders]
    assert any("rogue_registry.py" in p for p in paths)
