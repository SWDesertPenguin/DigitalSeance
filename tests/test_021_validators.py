# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 021 V16 validator unit tests (T011 of tasks.md).

Covers each of the three new SACP_* validators per spec 021 FR-002 /
FR-005 / FR-009 / FR-014 and contracts/env-vars.md:

- SACP_FILLER_THRESHOLD
- SACP_REGISTER_DEFAULT
- SACP_RESPONSE_SHAPING_ENABLED

Each validator: valid value passes (returns None); out-of-range value
returns a ValidationFailure naming the offending var; empty handled per
the var's allowed-empty rule (all three accept unset/empty).

Plus a drift-detection regression that temporarily strips one of the
three sections from docs/env-vars.md and runs scripts/check_env_vars.py
to confirm the V16 CI gate trips on validator-vs-docs drift, not just
on the present-and-aligned state.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.config import validators

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_VARS_DOC = REPO_ROOT / "docs" / "env-vars.md"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_env_vars.py"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the three spec-021 vars unset."""
    for var in (
        "SACP_FILLER_THRESHOLD",
        "SACP_REGISTER_DEFAULT",
        "SACP_RESPONSE_SHAPING_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SACP_FILLER_THRESHOLD
# ---------------------------------------------------------------------------


def test_filler_threshold_unset_passes() -> None:
    assert validators.validate_filler_threshold() is None


def test_filler_threshold_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", "")
    assert validators.validate_filler_threshold() is None


@pytest.mark.parametrize("value", ["0.0", "0.5", "0.6", "0.55", "1.0"])
def test_filler_threshold_in_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", value)
    assert validators.validate_filler_threshold() is None


@pytest.mark.parametrize("value", ["-0.001", "1.001", "1.5", "-1.0", "2.0"])
def test_filler_threshold_out_of_range(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", value)
    failure = validators.validate_filler_threshold()
    assert failure is not None
    assert failure.var_name == "SACP_FILLER_THRESHOLD"


@pytest.mark.parametrize("value", ["abc", "high", "0.5x"])
def test_filler_threshold_non_float(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_FILLER_THRESHOLD", value)
    failure = validators.validate_filler_threshold()
    assert failure is not None
    assert failure.var_name == "SACP_FILLER_THRESHOLD"
    assert "float" in failure.reason


# ---------------------------------------------------------------------------
# SACP_REGISTER_DEFAULT
# ---------------------------------------------------------------------------


def test_register_default_unset_passes() -> None:
    assert validators.validate_register_default() is None


def test_register_default_empty_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SACP_REGISTER_DEFAULT", "")
    assert validators.validate_register_default() is None


@pytest.mark.parametrize("value", ["1", "2", "3", "4", "5"])
def test_register_default_in_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_REGISTER_DEFAULT", value)
    assert validators.validate_register_default() is None


@pytest.mark.parametrize("value", ["0", "6", "-1", "10"])
def test_register_default_out_of_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_REGISTER_DEFAULT", value)
    failure = validators.validate_register_default()
    assert failure is not None
    assert failure.var_name == "SACP_REGISTER_DEFAULT"


@pytest.mark.parametrize("value", ["1.5", "two", "balanced"])
def test_register_default_non_integer(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_REGISTER_DEFAULT", value)
    failure = validators.validate_register_default()
    assert failure is not None
    assert failure.var_name == "SACP_REGISTER_DEFAULT"
    assert "integer" in failure.reason


# ---------------------------------------------------------------------------
# SACP_RESPONSE_SHAPING_ENABLED
# ---------------------------------------------------------------------------


def test_response_shaping_enabled_unset_passes() -> None:
    assert validators.validate_response_shaping_enabled() is None


def test_response_shaping_enabled_empty_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", "")
    assert validators.validate_response_shaping_enabled() is None


@pytest.mark.parametrize("value", ["true", "false", "True", "FALSE", "TRUE", "0", "1"])
def test_response_shaping_enabled_valid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", value)
    assert validators.validate_response_shaping_enabled() is None


@pytest.mark.parametrize("value", ["yes", "no", "on", "off", "2", "-1"])
def test_response_shaping_enabled_invalid(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SACP_RESPONSE_SHAPING_ENABLED", value)
    failure = validators.validate_response_shaping_enabled()
    assert failure is not None
    assert failure.var_name == "SACP_RESPONSE_SHAPING_ENABLED"


# ---------------------------------------------------------------------------
# Aggregate: all three validators registered in VALIDATORS tuple
# ---------------------------------------------------------------------------


def test_all_three_validators_registered() -> None:
    """T006 sanity: each of the three new validators is in the VALIDATORS tuple."""
    names = {v.__name__ for v in validators.VALIDATORS}
    assert "validate_filler_threshold" in names
    assert "validate_register_default" in names
    assert "validate_response_shaping_enabled" in names


# ---------------------------------------------------------------------------
# Drift-detection regression: V16 CI gate trips when a docs section is
# missing for an env var that has a validator. Per T011 sub-bullet:
# temporarily remove one of the three sections from docs/env-vars.md, run
# the check script, and assert it exits non-zero AND names the missing
# section. Restore the section before the test exits.
# ---------------------------------------------------------------------------


def _strip_section(text: str, var_name: str) -> str:
    r"""Remove the `### \`VAR\`` heading and everything until the next `###`."""
    heading = f"### `{var_name}`"
    start = text.find(heading)
    if start == -1:
        raise AssertionError(f"section {var_name} not found in env-vars.md")
    # Find the next "### " after the heading (start of next section).
    nxt = text.find("\n### ", start + len(heading))
    if nxt == -1:
        # Heading is last; strip to EOF.
        return text[:start].rstrip() + "\n"
    return text[:start] + text[nxt + 1 :]


def test_v16_ci_gate_trips_on_validator_vs_docs_drift(tmp_path: Path) -> None:
    """Removing one of the three sections from docs/env-vars.md MUST cause
    scripts/check_env_vars.py to exit non-zero AND name the missing section.
    Verifies the V16 CI gate trips on validator-vs-docs drift, not just on
    the present-and-aligned state.

    The test edits docs/env-vars.md in place and restores the original
    content in a finally block — no permanent change to the working tree.
    """
    original = ENV_VARS_DOC.read_text(encoding="utf-8")
    target_var = "SACP_FILLER_THRESHOLD"
    stripped = _strip_section(original, target_var)
    assert target_var not in stripped or f"### `{target_var}`" not in stripped
    try:
        ENV_VARS_DOC.write_text(stripped, encoding="utf-8")
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(CHECK_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert (
            result.returncode != 0
        ), "check_env_vars.py exited 0 but the docs section was stripped"
        combined = result.stdout + result.stderr
        assert (
            target_var in combined
        ), f"check_env_vars.py output did not name {target_var}; got: {combined}"
    finally:
        ENV_VARS_DOC.write_text(original, encoding="utf-8")
