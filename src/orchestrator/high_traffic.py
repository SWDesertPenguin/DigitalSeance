"""High-traffic session-mode configuration (spec 013).

Hosts ``HighTrafficSessionConfig`` and ``ObserverDowngradeThresholds`` —
the per-session config object that drives the three orthogonal
mechanisms (batching cadence, convergence threshold override,
observer downgrade). See specs/013-high-traffic-mode/data-model.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Defaults match docs/env-vars.md and the validators in src/config/validators.py.
_DEFAULT_RESTORE_WINDOW_S = 120


@dataclass(frozen=True, slots=True)
class ObserverDowngradeThresholds:
    """Per-session observer-downgrade trigger thresholds (013 §FR-008-FR-011)."""

    participants: int
    tpm: int
    restore_window_s: int = _DEFAULT_RESTORE_WINDOW_S


@dataclass(frozen=True, slots=True)
class HighTrafficSessionConfig:
    """Resolved per-session high-traffic config (013 mechanisms 1-3).

    ``None`` for any mechanism's field means that mechanism is disabled
    (env var unset). The full object is itself ``None`` when all three
    env vars are unset — the SC-005 regression-equivalence contract
    means callers short-circuit before reading any field in that case.
    """

    batch_cadence_s: int | None
    convergence_threshold_override: float | None
    observer_downgrade: ObserverDowngradeThresholds | None

    @classmethod
    def resolve_from_env(cls) -> HighTrafficSessionConfig | None:
        """Return the resolved config or None when all three env vars are unset.

        Validators in ``src/config/validators.py`` have already enforced
        well-formedness at startup (V16); this resolver assumes valid
        inputs and only re-parses for typing.
        """
        cadence = _read_int("SACP_HIGH_TRAFFIC_BATCH_CADENCE_S")
        override = _read_float("SACP_CONVERGENCE_THRESHOLD_OVERRIDE")
        thresholds = _read_observer_downgrade_thresholds()
        if cadence is None and override is None and thresholds is None:
            return None
        return cls(
            batch_cadence_s=cadence,
            convergence_threshold_override=override,
            observer_downgrade=thresholds,
        )


def _read_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _read_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


def _read_observer_downgrade_thresholds() -> ObserverDowngradeThresholds | None:
    raw = os.environ.get("SACP_OBSERVER_DOWNGRADE_THRESHOLDS")
    if raw is None or raw.strip() == "":
        return None
    parsed: dict[str, int] = {}
    for entry in [e.strip() for e in raw.split(",") if e.strip()]:
        key, _, val = entry.partition(":")
        parsed[key.strip()] = int(val.strip())
    return ObserverDowngradeThresholds(
        participants=parsed["participants"],
        tpm=parsed["tpm"],
        restore_window_s=parsed.get("restore_window_s", _DEFAULT_RESTORE_WINDOW_S),
    )
