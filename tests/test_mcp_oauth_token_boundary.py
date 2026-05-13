# SPDX-License-Identifier: AGPL-3.0-or-later
"""Architectural test: JWT imports must live only in src/mcp_protocol/auth/.

Spec 030 Phase 4 FR-099, SC-051.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
_AUTH_PKG = _SRC / "mcp_protocol" / "auth"


def _collect_import_names(path: Path) -> list[str]:
    """Return all module names imported in a Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_jwt_not_imported_outside_auth() -> None:
    violations = []
    for py in _SRC.rglob("*.py"):
        if py.is_relative_to(_AUTH_PKG):
            continue
        for name in _collect_import_names(py):
            if name == "jwt" or name.startswith("jwt."):
                violations.append(str(py.relative_to(_SRC)))
    assert violations == [], f"jwt imported outside auth/: {violations}"


def test_verify_access_token_not_called_outside_auth() -> None:
    violations = []
    for py in _SRC.rglob("*.py"):
        if py.is_relative_to(_AUTH_PKG):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "verify_access_token" in text and "from src.mcp_protocol.auth" not in text:
            violations.append(str(py.relative_to(_SRC)))
    assert violations == [], f"verify_access_token referenced outside auth/: {violations}"
