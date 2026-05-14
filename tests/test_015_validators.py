# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 015 validator unit tests (T013).

Covers all five validators:
  validate_provider_failure_threshold
  validate_provider_failure_window_s
  validate_provider_recovery_probe_backoff
  validate_provider_probe_timeout_s
  validate_provider_failure_paired_vars (cross-validator)
"""

from __future__ import annotations

import os


def _set(**kwargs: str) -> None:
    for k, v in kwargs.items():
        os.environ[k] = v


def _unset(*keys: str) -> None:
    for k in keys:
        os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# validate_provider_failure_threshold
# ---------------------------------------------------------------------------


class TestProviderFailureThreshold:
    def setup_method(self):
        _unset("SACP_PROVIDER_FAILURE_THRESHOLD")

    def teardown_method(self):
        _unset("SACP_PROVIDER_FAILURE_THRESHOLD")

    def test_unset_returns_none(self):
        from src.config.validators import validate_provider_failure_threshold

        assert validate_provider_failure_threshold() is None

    def test_valid_value_passes(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="5")
        assert validate_provider_failure_threshold() is None

    def test_lower_bound_passes(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="2")
        assert validate_provider_failure_threshold() is None

    def test_upper_bound_passes(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="100")
        assert validate_provider_failure_threshold() is None

    def test_below_range_fails(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="1")
        result = validate_provider_failure_threshold()
        assert result is not None
        assert "SACP_PROVIDER_FAILURE_THRESHOLD" in result.var_name

    def test_above_range_fails(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="101")
        result = validate_provider_failure_threshold()
        assert result is not None
        assert "SACP_PROVIDER_FAILURE_THRESHOLD" in result.var_name

    def test_non_integer_fails(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="abc")
        result = validate_provider_failure_threshold()
        assert result is not None

    def test_empty_string_returns_none(self):
        from src.config.validators import validate_provider_failure_threshold

        _set(SACP_PROVIDER_FAILURE_THRESHOLD="")
        assert validate_provider_failure_threshold() is None


# ---------------------------------------------------------------------------
# validate_provider_failure_window_s
# ---------------------------------------------------------------------------


class TestProviderFailureWindowS:
    def setup_method(self):
        _unset("SACP_PROVIDER_FAILURE_WINDOW_S")

    def teardown_method(self):
        _unset("SACP_PROVIDER_FAILURE_WINDOW_S")

    def test_unset_returns_none(self):
        from src.config.validators import validate_provider_failure_window_s

        assert validate_provider_failure_window_s() is None

    def test_valid_value_passes(self):
        from src.config.validators import validate_provider_failure_window_s

        _set(SACP_PROVIDER_FAILURE_WINDOW_S="60")
        assert validate_provider_failure_window_s() is None

    def test_lower_bound_passes(self):
        from src.config.validators import validate_provider_failure_window_s

        _set(SACP_PROVIDER_FAILURE_WINDOW_S="30")
        assert validate_provider_failure_window_s() is None

    def test_upper_bound_passes(self):
        from src.config.validators import validate_provider_failure_window_s

        _set(SACP_PROVIDER_FAILURE_WINDOW_S="3600")
        assert validate_provider_failure_window_s() is None

    def test_below_range_fails(self):
        from src.config.validators import validate_provider_failure_window_s

        _set(SACP_PROVIDER_FAILURE_WINDOW_S="29")
        result = validate_provider_failure_window_s()
        assert result is not None
        assert "SACP_PROVIDER_FAILURE_WINDOW_S" in result.var_name

    def test_above_range_fails(self):
        from src.config.validators import validate_provider_failure_window_s

        _set(SACP_PROVIDER_FAILURE_WINDOW_S="3601")
        result = validate_provider_failure_window_s()
        assert result is not None

    def test_non_integer_fails(self):
        from src.config.validators import validate_provider_failure_window_s

        _set(SACP_PROVIDER_FAILURE_WINDOW_S="3.14")
        result = validate_provider_failure_window_s()
        assert result is not None


# ---------------------------------------------------------------------------
# validate_provider_recovery_probe_backoff
# ---------------------------------------------------------------------------


class TestProviderRecoveryProbeBackoff:
    VAR = "SACP_PROVIDER_RECOVERY_PROBE_BACKOFF"

    def setup_method(self):
        _unset(self.VAR)

    def teardown_method(self):
        _unset(self.VAR)

    def test_unset_returns_none(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        assert validate_provider_recovery_probe_backoff() is None

    def test_single_valid_entry(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "10"})
        assert validate_provider_recovery_probe_backoff() is None

    def test_multiple_valid_entries(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "5,10,30,60"})
        assert validate_provider_recovery_probe_backoff() is None

    def test_entry_below_range_fails(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "0"})
        result = validate_provider_recovery_probe_backoff()
        assert result is not None

    def test_entry_above_range_fails(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "601"})
        result = validate_provider_recovery_probe_backoff()
        assert result is not None

    def test_too_many_entries_fails(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "1,2,3,4,5,6,7,8,9,10,11"})
        result = validate_provider_recovery_probe_backoff()
        assert result is not None

    def test_ten_entries_passes(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "1,2,3,4,5,6,7,8,9,10"})
        assert validate_provider_recovery_probe_backoff() is None

    def test_non_integer_entry_fails(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "5,abc,10"})
        result = validate_provider_recovery_probe_backoff()
        assert result is not None

    def test_bounds_pass(self):
        from src.config.validators import validate_provider_recovery_probe_backoff

        _set(**{self.VAR: "1,600"})
        assert validate_provider_recovery_probe_backoff() is None


# ---------------------------------------------------------------------------
# validate_provider_probe_timeout_s
# ---------------------------------------------------------------------------


class TestProviderProbeTimeoutS:
    VAR = "SACP_PROVIDER_PROBE_TIMEOUT_S"

    def setup_method(self):
        _unset(self.VAR)

    def teardown_method(self):
        _unset(self.VAR)

    def test_unset_returns_none(self):
        from src.config.validators import validate_provider_probe_timeout_s

        assert validate_provider_probe_timeout_s() is None

    def test_valid_value_passes(self):
        from src.config.validators import validate_provider_probe_timeout_s

        _set(**{self.VAR: "10"})
        assert validate_provider_probe_timeout_s() is None

    def test_lower_bound_passes(self):
        from src.config.validators import validate_provider_probe_timeout_s

        _set(**{self.VAR: "1"})
        assert validate_provider_probe_timeout_s() is None

    def test_upper_bound_passes(self):
        from src.config.validators import validate_provider_probe_timeout_s

        _set(**{self.VAR: "30"})
        assert validate_provider_probe_timeout_s() is None

    def test_zero_fails(self):
        from src.config.validators import validate_provider_probe_timeout_s

        _set(**{self.VAR: "0"})
        result = validate_provider_probe_timeout_s()
        assert result is not None
        assert "SACP_PROVIDER_PROBE_TIMEOUT_S" in result.var_name

    def test_above_range_fails(self):
        from src.config.validators import validate_provider_probe_timeout_s

        _set(**{self.VAR: "31"})
        result = validate_provider_probe_timeout_s()
        assert result is not None

    def test_non_integer_fails(self):
        from src.config.validators import validate_provider_probe_timeout_s

        _set(**{self.VAR: "ten"})
        result = validate_provider_probe_timeout_s()
        assert result is not None


# ---------------------------------------------------------------------------
# validate_provider_failure_paired_vars (cross-validator)
# ---------------------------------------------------------------------------


class TestProviderFailurePairedVars:
    T_VAR = "SACP_PROVIDER_FAILURE_THRESHOLD"
    W_VAR = "SACP_PROVIDER_FAILURE_WINDOW_S"

    def setup_method(self):
        _unset(self.T_VAR, self.W_VAR)

    def teardown_method(self):
        _unset(self.T_VAR, self.W_VAR)

    def test_both_unset_passes(self):
        from src.config.validators import validate_provider_failure_paired_vars

        assert validate_provider_failure_paired_vars() is None

    def test_both_set_passes(self):
        from src.config.validators import validate_provider_failure_paired_vars

        _set(**{self.T_VAR: "3", self.W_VAR: "60"})
        assert validate_provider_failure_paired_vars() is None

    def test_only_threshold_set_fails(self):
        from src.config.validators import validate_provider_failure_paired_vars

        _set(**{self.T_VAR: "3"})
        result = validate_provider_failure_paired_vars()
        assert result is not None
        assert "SACP_PROVIDER_FAILURE_WINDOW_S" in result.var_name

    def test_only_window_set_fails(self):
        from src.config.validators import validate_provider_failure_paired_vars

        _set(**{self.W_VAR: "60"})
        result = validate_provider_failure_paired_vars()
        assert result is not None
        assert "SACP_PROVIDER_FAILURE_THRESHOLD" in result.var_name
