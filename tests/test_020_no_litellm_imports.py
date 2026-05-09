"""FR-005 architectural test: no `import litellm` outside the LiteLLM adapter.

Walks `src/` and asserts no Python file outside `src/api_bridge/litellm/`
contains an `import litellm` or `from litellm` statement. Per
`tests/` the test will FAIL initially while `src/api_bridge/provider.py`
and `src/api_bridge/model_limits.py` still violate; the cutover (T035-T038
plus T076) clears the violations and the test transitions to passing.

The architectural constraint is enforced for `src/` only — tests under
`tests/` are permitted to import LiteLLM directly (they are
adapter-package unit tests by nature).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
ALLOWED_DIR = SRC_DIR / "api_bridge" / "litellm"

# Match a top-level or indented `import litellm` / `from litellm` statement.
# Does NOT match the same tokens inside a string literal (we only walk
# Python source files and look at logical line content, not string bodies).
_LITELLM_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+litellm|from\s+litellm[\s.])",
    re.MULTILINE,
)


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def test_no_litellm_imports_outside_adapter() -> None:
    """No file under `src/` outside `src/api_bridge/litellm/` may import litellm."""
    violations: list[tuple[Path, int, str]] = []
    for path in _iter_python_files(SRC_DIR):
        try:
            path.relative_to(ALLOWED_DIR)
        except ValueError:
            pass
        else:
            continue  # File is inside the allowed directory.
        text = path.read_text(encoding="utf-8")
        for match in _LITELLM_IMPORT_RE.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            violations.append((path.relative_to(REPO_ROOT), line_no, match.group(0).strip()))
    assert not violations, (
        "FR-005 architectural-test failure — files under src/ outside "
        "src/api_bridge/litellm/ import litellm:\n"
        + "\n".join(f"  {p}:{n}: {line}" for p, n, line in violations)
    )
