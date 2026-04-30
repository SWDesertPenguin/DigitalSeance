#!/usr/bin/env python3
"""Schema-mirror CI gate.

Fails the build when a column added via alembic migration is not reflected
in tests/conftest.py raw DDL. Closes the recurring drift class documented
in feedback_test_schema_mirror.md: local tests skip without Postgres so
mismatches surface only in CI.

Implementation: parse alembic SQL strings + conftest CREATE TABLE blocks
into {table: set(columns)} models and diff. No DB required.

Usage:
    python scripts/check_schema_mirror.py
    python scripts/check_schema_mirror.py --alembic-dir <path> --conftest <path>

Exit codes:
    0 = mirrored
    1 = drift (with diff on stderr)

Per spec 012 FR-008 / contracts/schema-mirror-ci.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALEMBIC_DIR = REPO_ROOT / "alembic" / "versions"
DEFAULT_CONFTEST = REPO_ROOT / "tests" / "conftest.py"

_CREATE_TABLE_HEAD_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(",
    re.IGNORECASE,
)
_ALTER_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)",
    re.IGNORECASE,
)
_CONSTRAINT_PREFIXES = (
    "PRIMARY KEY",
    "FOREIGN KEY",
    "UNIQUE ",
    "CONSTRAINT ",
    "CHECK ",
)


def _split_top_level(body: str) -> list[str]:
    """Split a CREATE TABLE body on commas at paren depth 0."""
    items: list[str] = []
    chunk: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(chunk))
            chunk = []
        else:
            chunk.append(ch)
    if chunk:
        items.append("".join(chunk))
    return items


def _column_name(item: str) -> str | None:
    """Return the column name from a CREATE TABLE item, or None for a constraint."""
    item = item.strip()
    if not item:
        return None
    upper = item.upper()
    for prefix in _CONSTRAINT_PREFIXES:
        if upper.startswith(prefix):
            return None
    tokens = item.split()
    if not tokens:
        return None
    return tokens[0].lower()


def _parse_columns(body: str) -> set[str]:
    """Extract column names from a CREATE TABLE column-list body."""
    cols: set[str] = set()
    for item in _split_top_level(body):
        name = _column_name(item)
        if name is not None:
            cols.add(name)
    return cols


def _read_balanced(text: str, start: int) -> str | None:
    """Read from `start` until the matching close paren; return inner body."""
    depth = 1
    chunk: list[str] = []
    for ch in text[start:]:
        if ch == "(":
            depth += 1
            chunk.append(ch)
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return "".join(chunk)
            chunk.append(ch)
        else:
            chunk.append(ch)
    return None


def _absorb_create_table(text: str, schema: dict[str, set[str]]) -> None:
    for match in _CREATE_TABLE_HEAD_RE.finditer(text):
        table = match.group(1).lower()
        body = _read_balanced(text, match.end())
        if body is None:
            continue
        cols = _parse_columns(body)
        schema.setdefault(table, set()).update(cols)


def _absorb_alter_add(text: str, schema: dict[str, set[str]]) -> None:
    for match in _ALTER_ADD_COLUMN_RE.finditer(text):
        table = match.group(1).lower()
        col = match.group(2).lower()
        schema.setdefault(table, set()).add(col)


def parse_alembic_schema(alembic_dir: Path) -> dict[str, set[str]]:
    """Walk alembic versions in revision order; build {table: cols}."""
    schema: dict[str, set[str]] = {}
    for path in sorted(alembic_dir.glob("[0-9]*.py")):
        text = path.read_text()
        _absorb_create_table(text, schema)
        _absorb_alter_add(text, schema)
    return schema


def parse_conftest_schema(conftest_path: Path) -> dict[str, set[str]]:
    """Parse conftest CREATE TABLE blocks into {table: cols}."""
    text = conftest_path.read_text()
    schema: dict[str, set[str]] = {}
    _absorb_create_table(text, schema)
    return schema


def diff_schemas(alembic: dict[str, set[str]], conftest: dict[str, set[str]]) -> list[str]:
    """Return drift messages; empty list = no drift."""
    msgs: list[str] = []
    for table, alembic_cols in alembic.items():
        conftest_cols = conftest.get(table)
        if conftest_cols is None:
            continue
        missing = alembic_cols - conftest_cols
        if missing:
            cols = ", ".join(sorted(missing))
            msgs.append(f"table '{table}': {cols} in alembic but not conftest")
    return msgs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alembic-dir", default=str(DEFAULT_ALEMBIC_DIR))
    parser.add_argument("--conftest", default=str(DEFAULT_CONFTEST))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    alembic_schema = parse_alembic_schema(Path(args.alembic_dir))
    conftest_schema = parse_conftest_schema(Path(args.conftest))
    msgs = diff_schemas(alembic_schema, conftest_schema)
    if msgs:
        print("schema mirror: FAIL", file=sys.stderr)
        for msg in msgs:
            print("  " + msg, file=sys.stderr)
        print(
            "\nTo resolve: edit tests/conftest.py raw DDL to match alembic.",
            file=sys.stderr,
        )
        print("See memory feedback_test_schema_mirror.md for context.", file=sys.stderr)
        return 1
    print(f"schema mirror: OK ({len(alembic_schema)} tables verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
