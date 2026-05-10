# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 shared-module-contracts.md freshness gate.

Catches drift between
``specs/029-audit-log-viewer/contracts/shared-module-contracts.md`` and
the modules it pins. If a future refactor moves a module without
updating the contract document, this test fails with a clear error.

Coverage:

- The four module paths cited in the contract MUST exist on disk.
- The two parity-gate scripts cited in the contract MUST exist on disk.
- The architectural-test path cited in the contract MUST exist on disk.
- Every audit action key declared in
  ``src/orchestrator/audit_labels.LABELS`` MUST also appear (verbatim)
  in the frontend mirror ``frontend/audit_labels.js``.

Note: this test does NOT re-run the parity gate, the architectural
test, or the WS event contract — those are separate test files. This
test is a structural sanity check that the citations in the contract
document still point at real artifacts.
"""

from __future__ import annotations

from pathlib import Path

from src.orchestrator.audit_labels import LABELS

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = (
    REPO_ROOT / "specs" / "029-audit-log-viewer" / "contracts" / "shared-module-contracts.md"
)

# Each entry: (relative_path, why_the_contract_cites_it)
EXPECTED_MODULE_PATHS: list[tuple[str, str]] = [
    ("src/orchestrator/audit_labels.py", "§1 backend action-label registry"),
    ("frontend/audit_labels.js", "§1 frontend action-label mirror"),
    ("src/orchestrator/time_format.py", "§2 backend time formatter"),
    ("frontend/time_format.js", "§2 frontend time formatter"),
    ("frontend/diff_engine.js", "§3 pure-logic diff engine"),
    ("frontend/app.jsx", "§3 inline DiffRenderer component host"),
]

EXPECTED_GATE_PATHS: list[tuple[str, str]] = [
    ("scripts/check_audit_label_parity.py", "§5 action-label parity gate"),
    ("scripts/check_time_format_parity.py", "§5 time-formatter parity gate"),
    ("tests/test_029_architectural.py", "§6 FR-020 architectural test"),
]


def test_contract_document_exists() -> None:
    assert (
        CONTRACT_PATH.is_file()
    ), f"shared-module-contracts.md missing at {CONTRACT_PATH.relative_to(REPO_ROOT)}"


def test_contract_cites_paths_that_exist_on_disk() -> None:
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    missing: list[str] = []
    for rel_path, citation in EXPECTED_MODULE_PATHS + EXPECTED_GATE_PATHS:
        on_disk = (REPO_ROOT / rel_path).is_file()
        cited = rel_path in contract_text
        if not on_disk:
            missing.append(f"{rel_path} ({citation}) — NOT ON DISK")
        elif not cited:
            missing.append(f"{rel_path} ({citation}) — NOT CITED IN CONTRACT")
    assert not missing, "shared-module-contracts.md is out of sync with the repo: " + "; ".join(
        missing
    )


def test_frontend_mirror_contains_every_backend_action_key() -> None:
    """Defensive: catches the case where the parity script breaks but the
    frontend file still parses. This compares verbatim string presence so
    a drift in either direction lights up here AND in the parity gate."""

    js_text = (REPO_ROOT / "frontend" / "audit_labels.js").read_text(encoding="utf-8")
    missing = [action for action in LABELS if f'"{action}"' not in js_text]
    assert not missing, (
        "frontend/audit_labels.js is missing entries the backend declares: " f"{sorted(missing)}"
    )


def test_size_thresholds_match_between_contract_and_module() -> None:
    """§3 / §4 lock the threshold constants. The contract document quotes
    50_000 / 500_000; the module's locked literal must match."""

    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    js_text = (REPO_ROOT / "frontend" / "diff_engine.js").read_text(encoding="utf-8")
    # JS keeps the literals without underscores (50000, 500000); accept either form.
    for value, alternates in (
        (50_000, ("50000", "50_000")),
        (500_000, ("500000", "500_000")),
    ):
        assert any(
            alt in js_text for alt in alternates
        ), f"diff_engine.js missing literal for threshold {value}"
    for token in ("50,000", "500,000"):
        assert token in contract_text, f"shared-module-contracts.md missing threshold token {token}"
