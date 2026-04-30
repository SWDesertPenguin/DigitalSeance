#!/usr/bin/env python3
"""FR-to-test traceability CI gate.

Asserts that every FR/SR marker in every spec has an entry in
docs/traceability/fr-to-test.md, and every entry references either a real
test path or carries an `untested` tag with a non-empty trigger note.

Deployment is incremental — only specs that have a section in the artifact
are checked. Specs absent from the artifact are skipped, allowing spec-by-spec
hand-curation under T021 to land as small PRs without blocking the gate.

Usage:
    python scripts/check_traceability.py
    python scripts/check_traceability.py --specs-dir <path> --artifact <path>

Exit codes:
    0 = clean (or artifact absent / empty)
    1 = drift (per-spec messages on stderr)

Per spec 012 FR-003 / contracts/traceability-artifact.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPECS_DIR = REPO_ROOT / "specs"
DEFAULT_ARTIFACT = REPO_ROOT / "docs" / "traceability" / "fr-to-test.md"

_FR_RE = re.compile(r"\*\*(FR-\d+[a-z]?|SR-\d+[a-z]?)\*\*")
_SECTION_RE = re.compile(r"^##\s+(\S+)")
_ROW_RE = re.compile(r"^\|\s*(FR-\d+[a-z]?|SR-\d+[a-z]?)\s*\|")


def _find_markers(spec_text: str) -> set[str]:
    """Extract FR/SR markers from a spec.md."""
    return {m.group(1) for m in _FR_RE.finditer(spec_text)}


def _spec_dirname(spec_path: Path) -> str:
    """Return the spec's directory name (e.g. '003-turn-loop-engine')."""
    return spec_path.parent.name


def _scan_specs(specs_dir: Path) -> dict[str, set[str]]:
    """Return {spec_dirname: set(markers)} for every specs/NNN-*/spec.md."""
    out: dict[str, set[str]] = {}
    for spec in sorted(specs_dir.glob("[0-9]*-*/spec.md")):
        out[_spec_dirname(spec)] = _find_markers(spec.read_text())
    return out


def _parse_row(line: str) -> dict[str, str] | None:
    """Parse a `| FR-NNN | tests | notes |` row."""
    if not _ROW_RE.match(line):
        return None
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if len(cells) < 2:
        return None
    return {
        "marker": cells[0],
        "tests": cells[1],
        "notes": cells[2] if len(cells) > 2 else "",
    }


def _parse_artifact(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse '## <spec>' sections and their FR/SR rows."""
    sections: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        section_match = _SECTION_RE.match(line)
        if section_match:
            current = section_match.group(1)
            sections[current] = []
            continue
        if current is None:
            continue
        row = _parse_row(line)
        if row is not None:
            sections[current].append(row)
    return sections


def _check_tests_cell(row: dict[str, str], repo_root: Path) -> str | None:
    """Return error message if the row's tests/notes are invalid; None if OK."""
    tests = row["tests"]
    if not tests:
        return "tests cell empty"
    if tests == "untested":
        if not row["notes"]:
            return "marked 'untested' but trigger note empty"
        return None
    for entry in tests.split(","):
        path_part = entry.strip().split("::")[0].strip("`")
        if not path_part:
            continue
        if not (repo_root / path_part).exists():
            return f"test file not found: {path_part}"
    return None


def _check_section(
    spec_name: str,
    spec_markers: set[str],
    rows: list[dict[str, str]],
    repo_root: Path,
) -> list[str]:
    """Validate one spec's section against its FR/SR markers."""
    msgs: list[str] = []
    artifact_markers = {row["marker"] for row in rows}
    missing = spec_markers - artifact_markers
    for marker in sorted(missing):
        msgs.append(f"  {spec_name}: {marker} has no traceability row")
    extra = artifact_markers - spec_markers
    for marker in sorted(extra):
        msgs.append(f"  {spec_name}: {marker} listed but not in spec")
    for row in rows:
        err = _check_tests_cell(row, repo_root)
        if err is not None:
            msgs.append(f"  {spec_name}: {row['marker']}: {err}")
    return msgs


def _validate(
    spec_markers: dict[str, set[str]],
    artifact_sections: dict[str, list[dict[str, str]]],
    repo_root: Path,
) -> tuple[list[str], int]:
    """Return (messages, count of specs checked)."""
    msgs: list[str] = []
    checked = 0
    for spec_name, markers in spec_markers.items():
        rows = artifact_sections.get(spec_name)
        if rows is None:
            continue
        checked += 1
        msgs.extend(_check_section(spec_name, markers, rows, repo_root))
    return msgs, checked


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs-dir", default=str(DEFAULT_SPECS_DIR))
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    specs_dir = Path(args.specs_dir)
    artifact_path = Path(args.artifact)
    repo_root = Path(args.repo_root)
    spec_markers = _scan_specs(specs_dir)
    if not artifact_path.exists():
        print("traceability: skipped (artifact not yet populated)")
        return 0
    artifact_sections = _parse_artifact(artifact_path.read_text())
    msgs, checked = _validate(spec_markers, artifact_sections, repo_root)
    if msgs:
        print("traceability: FAIL", file=sys.stderr)
        for msg in msgs:
            print(msg, file=sys.stderr)
        print(
            "\nTo resolve: edit docs/traceability/fr-to-test.md to add the "
            "missing rows, fix test paths, or add trigger notes for 'untested'.",
            file=sys.stderr,
        )
        return 1
    if checked == 0:
        print("traceability: skipped (no spec sections in artifact yet)")
        return 0
    print(f"traceability: OK ({checked} spec sections verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
