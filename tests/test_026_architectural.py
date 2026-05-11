# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 026 architectural tests — FR-023 + FR-024 (T022 + T047 expansion).

FR-023: no file under `src/` outside `src/compression/` may import a
concrete compressor (NoOpCompressor, LLMLingua2mBERTCompressor,
SelectiveContextCompressor, NoOpProvenceAdapter, NoOpLayer6Adapter)
directly. All access MUST go through `CompressorService.compress(...)`.

FR-024: the convergence-detector code path must NOT read the
per-participant compressed bridge view. Compressed segments MUST NOT
appear in convergence-window inputs. Enforced by asserting
src/orchestrator/convergence.py imports nothing from src.compression.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"

_CONCRETE_COMPRESSOR_MODULES = frozenset(
    {
        "noop",
        "llmlingua2_mbert",
        "selective_context",
        "provence",
        "layer6",
    }
)


def _scan_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _imports_from(tree: ast.Module) -> list[ast.ImportFrom]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]


def test_no_direct_compressor_imports_outside_compression_package() -> None:
    """FR-023: concrete compressor classes are internal to src/compression/."""
    offenders: list[tuple[str, str]] = []
    for src_file in _scan_python_files(SRC_ROOT):
        # The compression package itself + its registry module may import
        # the concrete classes for module-load registration.
        if "compression" in src_file.relative_to(SRC_ROOT).parts[:1]:
            continue
        tree = ast.parse(src_file.read_text(encoding="utf-8"))
        for node in _imports_from(tree):
            if node.module is None:
                continue
            tail = node.module.rsplit(".", maxsplit=1)[-1]
            if node.module.startswith("src.compression.") and tail in _CONCRETE_COMPRESSOR_MODULES:
                offenders.append((str(src_file.relative_to(REPO_ROOT)), node.module))
    assert offenders == [], (
        "files outside src/compression/ import concrete compressors directly; "
        f"use CompressorService instead — offenders: {offenders}"
    )


def test_convergence_detector_does_not_import_from_compression_package() -> None:
    """FR-024: convergence detector reads raw transcript, not compressed bridge view."""
    convergence_path = SRC_ROOT / "orchestrator" / "convergence.py"
    assert convergence_path.exists(), "expected src/orchestrator/convergence.py"
    tree = ast.parse(convergence_path.read_text(encoding="utf-8"))
    for node in _imports_from(tree):
        if node.module and node.module.startswith("src.compression"):
            raise AssertionError(
                f"src/orchestrator/convergence.py imports {node.module!r}; "
                f"the convergence detector MUST read the raw transcript, "
                f"NOT the compressed bridge view (spec 026 FR-024)"
            )


def test_density_signal_does_not_import_from_compression_package() -> None:
    """FR-024 extension: spec 004 density signal feeds convergence; same constraint applies."""
    density_path = SRC_ROOT / "orchestrator" / "density.py"
    assert density_path.exists(), "expected src/orchestrator/density.py"
    tree = ast.parse(density_path.read_text(encoding="utf-8"))
    for node in _imports_from(tree):
        if node.module and node.module.startswith("src.compression"):
            raise AssertionError(
                f"src/orchestrator/density.py imports {node.module!r}; "
                f"the density signal MUST read raw turn content, "
                f"NOT the compressed bridge view (spec 026 FR-024)"
            )


def test_compressor_service_does_not_call_unexpected_writes() -> None:
    """CompressorService MUST NOT issue DB writes other than the compression_log INSERT."""
    service_path = SRC_ROOT / "compression" / "service.py"
    source = service_path.read_text(encoding="utf-8")
    # Heuristic: no asyncpg / no execute() / no INSERT INTO present in the dispatcher.
    # All DB-side writes flow via the _telemetry_sink module's writer hook.
    forbidden = ("asyncpg", "execute(", "INSERT INTO")
    for token in forbidden:
        assert token not in source, (
            f"src/compression/service.py contains {token!r}; "
            f"CompressorService MUST delegate DB writes to "
            f"src/compression/_telemetry_sink.py's writer hook"
        )
