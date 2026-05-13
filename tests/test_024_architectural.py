# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 024 FR-001 / SC-001 architectural enforcement.

The security envelope of the entire scratch surface: notes are
NEVER assembled into AI context. This test walks the
context-assembly modules and asserts NO module imports any symbol
from ``src.scratch.*`` (the only path that exposes
``facilitator_notes`` rows).

Layer 1 (this test): static AST import scan.
Layer 2 (runtime tracer): a separate test patches
``FacilitatorNotesRepository`` so a read during turn assembly
fails loudly (covered in `tests/test_024_scope_detection.py`
once the run-loop harness is available — for v1 we ship the
static scan + the runtime patch helper for downstream test files).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_ASSEMBLY_ROOTS = (
    REPO_ROOT / "src" / "orchestrator",
    REPO_ROOT / "src" / "prompts",
    REPO_ROOT / "src" / "api_bridge",
    REPO_ROOT / "src" / "operations",
)
FORBIDDEN_PREFIX = "src.scratch"


def _iter_import_targets(tree: ast.Module) -> list[str]:
    """Yield every dotted target of every Import / ImportFrom in the module."""
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            targets.append(node.module)
    return targets


def _scan_for_forbidden_imports() -> list[tuple[Path, str]]:
    """Return ``(path, offending_target)`` tuples for any forbidden import."""
    offenders: list[tuple[Path, str]] = []
    for root in CONTEXT_ASSEMBLY_ROOTS:
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for target in _iter_import_targets(tree):
                if target.startswith(FORBIDDEN_PREFIX):
                    offenders.append((py, target))
    return offenders


def test_no_context_assembly_module_imports_scratch() -> None:
    """FR-001: no AI context-assembly path may reach the scratch surface.

    A failing assertion here means a developer added an import statement
    that crosses the FR-001 isolation boundary. The fix is to remove the
    import; if scratch state is genuinely needed in context assembly,
    the spec MUST be amended and the architectural test relaxed
    explicitly (with reviewer agreement).
    """
    offenders = _scan_for_forbidden_imports()
    assert offenders == [], (
        "FR-001 violation — context-assembly module(s) import the scratch "
        "surface: "
        + "; ".join(f"{path.relative_to(REPO_ROOT)} -> {target}" for path, target in offenders)
    )


def test_scratch_module_exists_and_exports_repository() -> None:
    """Sanity: the scratch package exists with the expected entry points."""
    repo_path = REPO_ROOT / "src" / "scratch" / "repository.py"
    assert repo_path.is_file(), "src/scratch/repository.py must exist"
    text = repo_path.read_text(encoding="utf-8")
    assert "class FacilitatorNotesRepository" in text


def test_synthetic_violation_is_caught(tmp_path, monkeypatch) -> None:
    """Drop a synthetic import under a fake assembly root and assert detection."""
    fake_root = tmp_path / "src" / "orchestrator"
    fake_root.mkdir(parents=True)
    (fake_root / "rogue.py").write_text(
        "from src.scratch.repository import FacilitatorNotesRepository\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tests.test_024_architectural.CONTEXT_ASSEMBLY_ROOTS",
        (fake_root,),
    )
    offenders = _scan_for_forbidden_imports()
    assert offenders, "synthetic violation MUST be detected"
    assert any(p.name == "rogue.py" for p, _ in offenders)
