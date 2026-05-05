#!/usr/bin/env python3
"""Run Checkmarx 2MS against the staged file paths passed as arguments.

Wired into `.pre-commit-config.yaml` as a `local` hook. Pre-commit invokes
this script with the staged file paths (relative to repo root) as positional
arguments.

2MS filesystem mode only accepts a single `--path` pointing at a folder, so
we stage the affected files into a temporary directory under the repo
(preserving their relative layout) and scan that. The temp dir is created
inside the repo because Docker Desktop is already configured to mount the
repo drive; system temp dirs aren't necessarily on a shared path.

This complements gitleaks (already wired earlier in the pre-commit config)
and the pre-push 2MS run (which scans full git history across all branches).
Two engines + two stages = layered coverage.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _stage_files(repo_root: Path, files: list[str], tmp_path: Path) -> int:
    copied = 0
    for rel in files:
        src = repo_root / rel
        if not src.is_file():
            continue
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


def _run_2ms(repo_posix: str, rel_tmp: str) -> int:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo_posix}:/repo:ro",
        "checkmarx/2ms:latest",
        "filesystem",
        "--path",
        f"/repo/{rel_tmp}",
        "--config",
        "/repo/.2ms.yaml",
    ]
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"
    # cmd is a fully-controlled literal list; no untrusted input is interpolated.
    return subprocess.run(cmd, env=env, check=False).returncode  # noqa: S603


def main() -> int:
    files = [f for f in sys.argv[1:] if f]
    if not files:
        return 0
    repo_root = Path(__file__).resolve().parent.parent
    repo_posix = str(repo_root).replace("\\", "/")
    with tempfile.TemporaryDirectory(dir=repo_root, prefix=".2ms-scan-") as tmp:
        tmp_path = Path(tmp)
        copied = _stage_files(repo_root, files, tmp_path)
        if copied == 0:
            return 0
        rel_tmp = tmp_path.relative_to(repo_root).as_posix()
        print(f"-> 2MS secret scan on {copied} staged file(s)...", flush=True)
        rc = _run_2ms(repo_posix, rel_tmp)
    if rc != 0:
        sys.stderr.write(
            "\nBLOCKED: 2MS detected secrets in staged files.\n"
            "  Override (use sparingly): git commit --no-verify\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
