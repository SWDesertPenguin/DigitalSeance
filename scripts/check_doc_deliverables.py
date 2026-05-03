#!/usr/bin/env python3
"""Doc-deliverable presence + coverage CI gate.

Asserts that:
  1. Every canonical doc named in spec 012 FR-010 exists at the expected
     path with non-zero size.
  2. Every HTTP status code emitted from `src/` (HTTPException /
     JSONResponse / Response with `status_code=NNN`) appears in
     `docs/error-codes.md`.
  3. Every WS close code emitted from `src/web_ui/websocket.py` (close
     constants `CLOSE_*` and `WS_NNNN`) appears in
     `docs/error-codes.md`.
  4. Every WS event-type literal defined in `src/web_ui/events.py` via
     `_envelope("name", ...)` has a `### `name`` section in
     `docs/ws-events.md`.

Per spec 012 FR-010 / contracts/doc-deliverables.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC_DIR = REPO_ROOT / "src"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs"

CANONICAL_DOCS = (
    "env-vars.md",
    "error-codes.md",
    "ws-events.md",
    "glossary.md",
    "retention.md",
    "state-machines.md",
    # roles-permissions.md is intentionally kept local-only at
    # local/docs/roles-permissions.md per the US5 publication-scope
    # decision (2026-05-02): the role × permission matrix is
    # concentrated recon value and not shipped to public docs/.
    # Other US5 docs strip cross-references to it before shipping.
    "compliance-mapping.md",
    "operational-runbook.md",
)

# HTTP error status codes (>= 400) emitted at any call site we care about.
# 2xx / 3xx are catalog-of-errors out-of-scope per docs/error-codes.md.
_STATUS_RE = re.compile(r"status_code\s*=\s*([4-5]\d{2})")
# WS close codes — both literal `code=NNNN` and `code=CLOSE_FOO` constants.
_CLOSE_LITERAL_RE = re.compile(r"close\(\s*code\s*=\s*(\d{4})")
_CLOSE_CONST_RE = re.compile(r"close\(\s*code\s*=\s*(CLOSE_[A-Z_]+|status\.WS_\d{4}\w*)")
# `CLOSE_FOO = NNNN` constant definitions.
_CLOSE_DEF_RE = re.compile(r"^(CLOSE_[A-Z_]+)\s*=\s*(\d{4})", re.MULTILINE)
# `_envelope("name", ...)` call sites — every WS event helper goes through this.
_ENVELOPE_RE = re.compile(r'_envelope\(\s*"([a-z_]+)"')


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_presence(docs_dir: Path) -> list[str]:
    """Return drift messages for missing or empty canonical docs."""
    msgs: list[str] = []
    for name in CANONICAL_DOCS:
        path = docs_dir / name
        if not path.exists():
            msgs.append(f"  docs/{name}: missing")
        elif path.stat().st_size == 0:
            msgs.append(f"  docs/{name}: empty")
    return msgs


def _scan_status_codes(src_dir: Path) -> set[str]:
    """Return the set of HTTP status code literals found under src/."""
    found: set[str] = set()
    for path in src_dir.rglob("*.py"):
        found.update(_STATUS_RE.findall(_read(path)))
    return found


def _resolve_close_constants(src_dir: Path) -> dict[str, str]:
    """Return {const_name: numeric_code} for every CLOSE_* constant defined."""
    mapping: dict[str, str] = {}
    for path in src_dir.rglob("*.py"):
        for match in _CLOSE_DEF_RE.finditer(_read(path)):
            mapping[match.group(1)] = match.group(2)
    return mapping


def _scan_close_codes(src_dir: Path, consts: dict[str, str]) -> set[str]:
    """Return the set of WS close code literals (resolved from constants)."""
    found: set[str] = set()
    for path in src_dir.rglob("*.py"):
        text = _read(path)
        found.update(_CLOSE_LITERAL_RE.findall(text))
        for ref in _CLOSE_CONST_RE.findall(text):
            if ref in consts:
                found.add(consts[ref])
            elif ref.startswith("status.WS_"):
                # Match the digits inside e.g. "status.WS_1011_INTERNAL_ERROR".
                digits = re.search(r"WS_(\d{4})", ref)
                if digits:
                    found.add(digits.group(1))
    return found


def _scan_event_types(events_path: Path) -> set[str]:
    """Return the set of WS event-type literals declared in events.py."""
    if not events_path.exists():
        return set()
    return set(_ENVELOPE_RE.findall(_read(events_path)))


def _check_codes_documented(codes: set[str], doc_text: str, label: str) -> list[str]:
    """Assert every code literal appears as a substring of doc_text."""
    msgs: list[str] = []
    for code in sorted(codes):
        if code not in doc_text:
            msgs.append(f"  {label} {code}: emitted in src/ but absent from docs/error-codes.md")
    return msgs


def _check_events_documented(events: set[str], doc_text: str) -> list[str]:
    """Assert every event has a `### `<name>`` heading in ws-events.md."""
    msgs: list[str] = []
    for name in sorted(events):
        heading = f"### `{name}`"
        if heading not in doc_text:
            msgs.append(
                f"  WS event '{name}': declared in events.py but no section in "
                f"docs/ws-events.md",
            )
    return msgs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC_DIR))
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    return parser.parse_args()


def _gather_drift(src_dir: Path, docs_dir: Path) -> list[str]:
    """Run all checks and return the combined drift list."""
    msgs = _check_presence(docs_dir)
    err_path = docs_dir / "error-codes.md"
    ws_path = docs_dir / "ws-events.md"
    err_text = _read(err_path) if err_path.exists() else ""
    ws_text = _read(ws_path) if ws_path.exists() else ""
    consts = _resolve_close_constants(src_dir)
    msgs.extend(_check_codes_documented(_scan_status_codes(src_dir), err_text, "HTTP"))
    msgs.extend(_check_codes_documented(_scan_close_codes(src_dir, consts), err_text, "WS close"))
    events_path = src_dir / "web_ui" / "events.py"
    msgs.extend(_check_events_documented(_scan_event_types(events_path), ws_text))
    return msgs


def main() -> int:
    args = _parse_args()
    src_dir = Path(args.src_dir)
    docs_dir = Path(args.docs_dir)
    msgs = _gather_drift(src_dir, docs_dir)
    if msgs:
        print("doc-deliverables: FAIL", file=sys.stderr)
        for msg in msgs:
            print(msg, file=sys.stderr)
        print(
            "\nTo resolve: add the missing doc section, or amend the "
            "spec to remove the unreferenced code path.",
            file=sys.stderr,
        )
        return 1
    print(f"doc-deliverables: OK ({len(CANONICAL_DOCS)} docs present, codes + events covered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
