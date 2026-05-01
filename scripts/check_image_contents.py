#!/usr/bin/env python3
"""Release-readiness check: assert a built image has the right /app contents.

Audit M-09. Runs as a step in `.github/workflows/build-image.yml` after
the build + trivy scan, before the image is treated as releasable. Two
classes of failure trip a non-zero exit:

  REQUIRED — these directories MUST be present under /app:
    - src/run_apps.py        (the entrypoint module)
    - alembic/               (migrations)
    - alembic.ini            (alembic config)
    - frontend/              (UI assets)

  FORBIDDEN — these patterns MUST NOT appear under /app (they slipped
  past .dockerignore in the past):
    - .env / .env.* / *.env  (operator secrets — never bake in)
    - .git / .gitignore / .gitattributes
    - tests/                 (unit/integration tests don't belong in runtime)
    - specs/ / docs/         (spec + doc trees)
    - .venv/ / venv/         (host virtualenvs)
    - .vscode/ / .idea/ / .pytest_cache/ / .ruff_cache/

Forbidden checks are scoped to `/app` because Python's site-packages
under `/usr/local/lib/python3.14/site-packages` legitimately contain
`__pycache__/` directories — narrowing scope avoids false positives.

Usage:
    python scripts/check_image_contents.py <image-ref>

Exit code 0 = pass, 1 = required missing or forbidden present, 2 = docker
not available / image not pullable.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

REQUIRED_PATHS = (
    "/app/src/run_apps.py",
    "/app/alembic",
    "/app/alembic.ini",
    "/app/frontend",
)

FORBIDDEN_PATTERNS = (
    # Secrets
    ".env",
    "*.env",
    # VCS
    ".git",
    ".gitignore",
    ".gitattributes",
    # Dev trees
    "tests",
    "specs",
    "docs",
    # Local virtualenvs
    ".venv",
    "venv",
    # IDE / cache
    ".vscode",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
)


def _docker_available() -> bool:
    """Return True iff `docker` is on PATH and responsive."""
    if shutil.which("docker") is None:
        return False
    proc = subprocess.run(  # noqa: S603
        ["docker", "version", "--format", "{{.Server.Version}}"],  # noqa: S607
        capture_output=True,
        timeout=10,
        check=False,
    )
    return proc.returncode == 0


def _check_required(image: str) -> list[str]:
    """Return paths from REQUIRED_PATHS that are absent inside `image`."""
    missing: list[str] = []
    for path in REQUIRED_PATHS:
        cmd = ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", f"test -e {path}"]
        proc = subprocess.run(  # noqa: S603, S607
            cmd,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            missing.append(path)
    return missing


def _build_find_command() -> str:
    """Build the find expression that lists forbidden matches under /app."""
    name_clauses = " -o ".join(f"-name '{p}'" for p in FORBIDDEN_PATTERNS)
    return f"find /app \\( {name_clauses} \\) -print 2>/dev/null"


def _check_forbidden(image: str) -> list[str]:
    """Return forbidden paths actually present under /app inside `image`."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "sh",
        image,
        "-c",
        _build_find_command(),
    ]
    proc = subprocess.run(  # noqa: S603, S607
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        return [f"<find failed: {proc.stderr.strip()}>"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _print_report(missing: list[str], forbidden: list[str]) -> None:
    """Print a human-readable failure report to stderr."""
    if missing:
        print("MISSING required paths in image:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
    if forbidden:
        print("FORBIDDEN paths present in image /app:", file=sys.stderr)
        for path in forbidden:
            print(f"  - {path}", file=sys.stderr)


def main(argv: list[str]) -> int:
    """Run required + forbidden checks against `argv[0]`; return exit code."""
    if not argv:
        print("usage: check_image_contents.py <image-ref>", file=sys.stderr)
        return 2
    image = argv[0]
    if not _docker_available():
        print("docker not available; cannot inspect image contents", file=sys.stderr)
        return 2
    missing = _check_required(image)
    forbidden = _check_forbidden(image)
    if not missing and not forbidden:
        print(f"image {image}: OK ({len(REQUIRED_PATHS)} required paths present)")
        return 0
    _print_report(missing, forbidden)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
