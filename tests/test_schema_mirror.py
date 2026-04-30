"""Meta-tests for scripts/check_schema_mirror.py.

Verifies the schema-mirror gate (spec 012 FR-008 / contracts/schema-mirror-ci.md):
- Current repo state passes (alembic 008 columns are mirrored in conftest)
- Synthetic drift is detected (column added in alembic but absent from conftest)
- A constraint-only line (PRIMARY KEY (...)) is not mistaken for a column
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_schema_mirror.py"


def _run(*extra_args: str) -> subprocess.CompletedProcess[str]:
    # S603: input is sys.executable + a fixed script path under repo control;
    # extra_args come from the tests themselves. No untrusted input.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), *extra_args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_current_repo_passes():
    """After feature 012 Phase A, alembic 008 columns are mirrored in conftest."""
    result = _run()
    assert result.returncode == 0, f"unexpected drift: {result.stderr}"
    assert "schema mirror: OK" in result.stdout


def test_drift_detected(tmp_path: Path):
    """Column added in alembic but absent from conftest is flagged."""
    alembic_dir = tmp_path / "versions"
    alembic_dir.mkdir()
    (alembic_dir / "001_init.py").write_text(
        'op.execute("""CREATE TABLE foo (id INTEGER PRIMARY KEY, bar TEXT)""")\n'
        'op.execute("ALTER TABLE foo ADD COLUMN baz INTEGER")\n'
    )
    conftest = tmp_path / "conftest.py"
    conftest.write_text('_FOO_DDL = """CREATE TABLE foo (id INTEGER PRIMARY KEY)"""\n')
    result = _run("--alembic-dir", str(alembic_dir), "--conftest", str(conftest))
    assert result.returncode == 1
    assert "bar" in result.stderr
    assert "baz" in result.stderr


def test_matching_schemas_pass(tmp_path: Path):
    """Synthetic alembic + conftest with matching columns pass cleanly."""
    alembic_dir = tmp_path / "versions"
    alembic_dir.mkdir()
    (alembic_dir / "001_init.py").write_text(
        'op.execute("""CREATE TABLE foo (id INTEGER PRIMARY KEY, bar TEXT)""")\n'
    )
    conftest = tmp_path / "conftest.py"
    conftest.write_text('_FOO_DDL = """CREATE TABLE foo (id INTEGER PRIMARY KEY, bar TEXT)"""\n')
    result = _run("--alembic-dir", str(alembic_dir), "--conftest", str(conftest))
    assert result.returncode == 0


def test_constraint_lines_not_treated_as_columns(tmp_path: Path):
    """PRIMARY KEY (...) and FOREIGN KEY (...) lines must not register as columns."""
    alembic_dir = tmp_path / "versions"
    alembic_dir.mkdir()
    (alembic_dir / "001_init.py").write_text(
        'op.execute("""\n'
        "CREATE TABLE foo (\n"
        "    a INTEGER,\n"
        "    b INTEGER,\n"
        "    PRIMARY KEY (a, b),\n"
        "    FOREIGN KEY (a) REFERENCES other(id)\n"
        ')""")\n'
    )
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        '_FOO_DDL = """\n'
        "CREATE TABLE foo (\n"
        "    a INTEGER,\n"
        "    b INTEGER,\n"
        "    PRIMARY KEY (a, b),\n"
        "    FOREIGN KEY (a) REFERENCES other(id)\n"
        ')"""\n'
    )
    result = _run("--alembic-dir", str(alembic_dir), "--conftest", str(conftest))
    assert result.returncode == 0
