#!/usr/bin/env python3
"""SACP_* env-var coverage CI gate.

Asserts that every `SACP_*` variable read in `src/` has:
  1. A section in `docs/env-vars.md` (under either Validated or Reserved).
  2. If documented as Validated, a matching function in
     `src/config/validators.py`.

Closes the drift class where a new env var lands in code without a
validator or a doc entry — operators would have no way to know what
values are valid.

Per spec 012 FR-005 / contracts/env-vars-doc.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC_DIR = REPO_ROOT / "src"
DEFAULT_DOC = REPO_ROOT / "docs" / "env-vars.md"
DEFAULT_VALIDATORS = REPO_ROOT / "src" / "config" / "validators.py"

# Match os.environ.get("SACP_X") / os.environ["SACP_X"] / os.getenv("SACP_X")
_ENV_REF_RE = re.compile(
    r"""os\.(?:environ\s*[.\[]\s*(?:get\s*\(\s*)?|getenv\s*\(\s*)
        ['"](SACP_[A-Z_]+)['"]""",
    re.VERBOSE,
)
# Match `### \`SACP_X\`` headings in env-vars.md.
_DOC_HEADING_RE = re.compile(r"^###\s+`(SACP_[A-Z_]+)`", re.MULTILINE)
# Match `validators.validate_<x>` references inside doc sections.
_VALIDATOR_REF_RE = re.compile(r"`validators\.(validate_\w+)`")
# Match `def validate_<x>` definitions in validators.py.
_VALIDATOR_DEF_RE = re.compile(r"^def\s+(validate_\w+)\s*\(", re.MULTILINE)
# Match `Status: Reserved` markers under doc sections.
_RESERVED_RE = re.compile(r"\*\*Status\*\*:\s*Reserved", re.IGNORECASE)


def _scan_code(src_dir: Path) -> set[str]:
    """Return the set of SACP_* names referenced in src/ Python files."""
    found: set[str] = set()
    for path in src_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(_ENV_REF_RE.findall(text))
    return found


def _parse_doc_sections(doc_path: Path) -> dict[str, str]:
    """Return {var_name: section_body}; section_body is text until next ###."""
    text = doc_path.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    matches = list(_DOC_HEADING_RE.finditer(text))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[start:end]
    return sections


def _validator_names(validators_path: Path) -> set[str]:
    """Return the set of `validate_*` function names defined in validators.py."""
    text = validators_path.read_text(encoding="utf-8")
    return set(_VALIDATOR_DEF_RE.findall(text))


def _check_doc_for_var(
    var: str,
    section: str,
    validators: set[str],
) -> list[str]:
    """Return drift messages for a single var; empty list = clean."""
    msgs: list[str] = []
    if _RESERVED_RE.search(section):
        return msgs
    refs = _VALIDATOR_REF_RE.findall(section)
    if not refs:
        msgs.append(f"  {var}: docs needs `validators.validate_*` ref or Reserved marker")
        return msgs
    for ref in refs:
        if ref not in validators:
            msgs.append(f"  {var}: docs reference `validators.{ref}` not found in validators.py")
    return msgs


def _diff(
    code_vars: set[str],
    sections: dict[str, str],
    validators: set[str],
) -> list[str]:
    """Compute all drift messages."""
    msgs: list[str] = []
    for var in sorted(code_vars):
        if var not in sections:
            msgs.append(f"  {var}: read in src/ but no section in docs/env-vars.md")
            continue
        msgs.extend(_check_doc_for_var(var, sections[var], validators))
    return msgs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-dir", default=str(DEFAULT_SRC_DIR))
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    parser.add_argument("--validators", default=str(DEFAULT_VALIDATORS))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    code_vars = _scan_code(Path(args.src_dir))
    sections = _parse_doc_sections(Path(args.doc))
    validators = _validator_names(Path(args.validators))
    msgs = _diff(code_vars, sections, validators)
    if msgs:
        print("env-vars: FAIL", file=sys.stderr)
        for msg in msgs:
            print(msg, file=sys.stderr)
        print(
            "\nTo resolve: add the missing section to docs/env-vars.md, add the "
            "validate_* function to src/config/validators.py, or mark the var "
            "Reserved in the doc per the contract.",
            file=sys.stderr,
        )
        return 1
    print(f"env-vars: OK ({len(code_vars)} vars in src/, {len(sections)} sections in docs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
