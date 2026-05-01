#!/usr/bin/env python3
"""Refuse any commit that introduces a placeholder-secret literal.

Audit M-06. The V16 startup validators in `src/config/validators.py`
already refuse to bind ports if `SACP_DATABASE_URL` / `SACP_ENCRYPTION_KEY`
contain the placeholder strings below at runtime -- but that defends only
against operators forgetting to swap `.env.example` → `.env`. A committed
config file (Compose override, k8s secret YAML, sample tfvars, etc.)
carrying `changeme` or `REPLACE_ME_BEFORE_FIRST_RUN` would still leak
through code review and lock developers into a bad fixture.

This hook scans the file paths it's invoked with for the placeholder
patterns and exits non-zero on the first match. `.env.example` is
intentionally excluded by the pre-commit hook config -- that's where the
canonical placeholder lives.

Patterns are kept in lockstep with `_PLACEHOLDER_PATTERNS` in
`src/config/validators.py`. If you add one there, mirror it here.

Usage: invoked via .pre-commit-config.yaml (no-placeholder-secrets).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLACEHOLDER_PATTERNS = (
    "changeme",
    "REPLACE_ME_BEFORE_FIRST_RUN",
    "generate-with-python-fernet",
)


def _scan(path: Path) -> list[tuple[int, str, str]]:
    """Return a list of (line_no, pattern_matched, matching_line) for `path`."""
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for pattern in _PLACEHOLDER_PATTERNS:
            if pattern.lower() in lowered:
                findings.append((line_no, pattern, line.rstrip()))
                break
    return findings


def main(argv: list[str]) -> int:
    """Scan each argv path; return 1 if any placeholder appears, 0 otherwise."""
    exit_code = 0
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            continue
        for line_no, pattern, line in _scan(path):
            print(
                f"{path}:{line_no}: placeholder secret {pattern!r} -- replace before commit",
                file=sys.stderr,
            )
            print(f"  {line}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
