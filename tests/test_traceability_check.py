# SPDX-License-Identifier: AGPL-3.0-or-later

"""Meta-tests for scripts/check_traceability.py.

Verifies the FR-to-test traceability gate (spec 012 FR-003 /
contracts/traceability-artifact.md):
- Skipped cleanly when the artifact doesn't exist (incremental-adoption mode)
- Passes when an artifact section matches the spec's FR set
- Flags FRs in spec but missing from artifact
- Flags FRs in artifact but absent from spec
- Flags 'untested' rows lacking a trigger note
- Flags rows referencing a nonexistent test path
- Skips specs without a section in the artifact (allows per-spec rollout)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_traceability.py"


def _run(
    *,
    specs_dir: Path | None = None,
    artifact: Path | None = None,
    repo_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    args: list[str] = []
    if specs_dir is not None:
        args.extend(["--specs-dir", str(specs_dir)])
    if artifact is not None:
        args.extend(["--artifact", str(artifact)])
    if repo_root is not None:
        args.extend(["--repo-root", str(repo_root)])
    # S603: input is sys.executable + a fixed script path under repo control.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _write_spec(specs_dir: Path, name: str, markers: list[str]) -> None:
    spec_dir = specs_dir / name
    spec_dir.mkdir()
    body_lines = ["# Test spec\n", "## Requirements\n"]
    body_lines.extend(f"- **{m}**: synthetic\n" for m in markers)
    (spec_dir / "spec.md").write_text("".join(body_lines))


def _write_artifact(path: Path, sections: dict[str, list[tuple[str, str, str]]]) -> None:
    lines = ["# FR-to-Test Traceability\n"]
    for section, rows in sections.items():
        lines.append(f"\n## {section}\n\n")
        lines.append("| FR | Tests | Notes |\n")
        lines.append("|---|---|---|\n")
        for marker, tests, notes in rows:
            lines.append(f"| {marker} | {tests} | {notes} |\n")
    path.write_text("".join(lines))


def test_current_repo_passes():
    """No artifact yet → skipped (exit 0)."""
    result = _run()
    assert result.returncode == 0
    assert "skipped" in result.stdout or "OK" in result.stdout


def test_matching_spec_and_artifact_pass(tmp_path: Path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_spec(specs, "001-foo", ["FR-001", "FR-002"])
    artifact = tmp_path / "artifact.md"
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_x(): pass\n")
    _write_artifact(
        artifact,
        {
            "001-foo": [
                ("FR-001", "tests/test_foo.py::test_x", ""),
                ("FR-002", "untested", "Phase 3 trigger"),
            ]
        },
    )
    result = _run(specs_dir=specs, artifact=artifact, repo_root=tmp_path)
    assert result.returncode == 0, result.stderr


def test_missing_fr_in_artifact_fails(tmp_path: Path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_spec(specs, "001-foo", ["FR-001", "FR-002"])
    artifact = tmp_path / "artifact.md"
    _write_artifact(artifact, {"001-foo": [("FR-001", "untested", "later")]})
    result = _run(specs_dir=specs, artifact=artifact, repo_root=tmp_path)
    assert result.returncode == 1
    assert "FR-002" in result.stderr
    assert "no traceability row" in result.stderr


def test_extra_fr_in_artifact_fails(tmp_path: Path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_spec(specs, "001-foo", ["FR-001"])
    artifact = tmp_path / "artifact.md"
    _write_artifact(
        artifact,
        {
            "001-foo": [
                ("FR-001", "untested", "later"),
                ("FR-099", "untested", "later"),
            ]
        },
    )
    result = _run(specs_dir=specs, artifact=artifact, repo_root=tmp_path)
    assert result.returncode == 1
    assert "FR-099" in result.stderr
    assert "not in spec" in result.stderr


def test_untested_without_trigger_fails(tmp_path: Path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_spec(specs, "001-foo", ["FR-001"])
    artifact = tmp_path / "artifact.md"
    _write_artifact(artifact, {"001-foo": [("FR-001", "untested", "")]})
    result = _run(specs_dir=specs, artifact=artifact, repo_root=tmp_path)
    assert result.returncode == 1
    assert "trigger note empty" in result.stderr


def test_nonexistent_test_path_fails(tmp_path: Path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_spec(specs, "001-foo", ["FR-001"])
    artifact = tmp_path / "artifact.md"
    _write_artifact(
        artifact,
        {"001-foo": [("FR-001", "tests/nonexistent.py::test_x", "")]},
    )
    result = _run(specs_dir=specs, artifact=artifact, repo_root=tmp_path)
    assert result.returncode == 1
    assert "test file not found" in result.stderr


def test_unpopulated_spec_skipped(tmp_path: Path):
    """A spec with FRs but no artifact section is skipped (incremental rollout)."""
    specs = tmp_path / "specs"
    specs.mkdir()
    _write_spec(specs, "001-foo", ["FR-001", "FR-002"])
    _write_spec(specs, "002-bar", ["FR-001"])
    artifact = tmp_path / "artifact.md"
    # Only 001-foo has a section; 002-bar should be skipped.
    test_file = tmp_path / "tests" / "test_foo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_x(): pass\n")
    _write_artifact(
        artifact,
        {
            "001-foo": [
                ("FR-001", "tests/test_foo.py::test_x", ""),
                ("FR-002", "untested", "later"),
            ]
        },
    )
    result = _run(specs_dir=specs, artifact=artifact, repo_root=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "1 spec sections verified" in result.stdout
