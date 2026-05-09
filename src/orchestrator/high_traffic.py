"""High-traffic session-mode configuration (spec 013).

Hosts ``HighTrafficSessionConfig`` and ``ObserverDowngradeThresholds`` —
the per-session config object that drives the three orthogonal
mechanisms (batching cadence, convergence threshold override,
observer downgrade). See specs/013-high-traffic-mode/data-model.md.

Spec 014 extension (research.md §4): adds a controller-only
``MechanismActivation`` companion the DMA controller flips at runtime.
The activation state defaults to "engaged when env var is set"
(spec-013 baseline). When the activation flag is False, the call-site
short-circuits even though the env var IS set — that's the auto-apply
DISENGAGE path. The frozen ``HighTrafficSessionConfig`` itself stays
immutable — only the activation flags mutate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

MechanismName = Literal["batching", "convergence_override", "observer_downgrade"]

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


@dataclass(slots=True)
class MechanismActivation:
    """Controller-only mutable active flags for spec 013's mechanisms.

    Spec 014 (research.md §4): the DMA controller flips these flags in its
    auto-apply path. The activation flag is consulted ALONGSIDE the
    spec-013 env-var-derived config — a mechanism is active iff its env
    var is set AND its activation flag is True.

    Default state mirrors spec-013 baseline: all True. So with no
    controller running, mechanisms behave identically to pre-014 (the
    SC-004 additive-when-unset guarantee).
    """

    batching: bool = True
    convergence_override: bool = True
    observer_downgrade: bool = True

    def is_active(self, name: MechanismName) -> bool:
        """Return True iff the named mechanism's activation flag is True."""
        return bool(getattr(self, name))

    def engage_mechanism(self, name: MechanismName) -> None:
        """Spec 014 controller-only mutator: flip the named mechanism on.

        Per research §4: the spec-013 mechanism call-site reads
        ``(config is not None) AND activation.is_active(name)``. Engaging an
        unconfigured mechanism (env var unset) is a no-op at the call site
        because the config field is None. The controller still records
        ``skipped_mechanisms[]`` in the audit row in that case.
        """
        setattr(self, name, True)

    def disengage_mechanism(self, name: MechanismName) -> None:
        """Spec 014 controller-only mutator: flip the named mechanism off.

        Per research §4: disengage is always allowed; the call-site short-
        circuits before reading any state. No-op if already False.
        """
        setattr(self, name, False)


@dataclass(slots=True)
class HighTrafficRuntime:
    """Per-session runtime bundle: frozen config + mutable activation flags.

    The ``ConversationLoop`` holds one of these per session lifetime. Its
    ``activation`` field is the surface the DMA controller toggles in the
    auto-apply path. The ``config`` field stays frozen — env-var-derived
    thresholds never change at runtime per spec 013's contract.
    """

    config: HighTrafficSessionConfig | None
    activation: MechanismActivation = field(default_factory=MechanismActivation)

    def is_mechanism_engaged(self, name: MechanismName) -> bool:
        """True iff the named mechanism is configured (env var set) AND active.

        Single read-side check used by spec-013 call-sites to short-circuit:
        when False, the mechanism behaves as if its env var were unset,
        regardless of whether activation was just disengaged or the env
        var was never set.
        """
        if self.config is None:
            return False
        configured = _mechanism_is_configured(self.config, name)
        return configured and self.activation.is_active(name)

    def engage_mechanism(self, name: MechanismName) -> bool:
        """Engage and return True iff the mechanism's env var is configured.

        Returns False (caller logs a skip into ``skipped_mechanisms[]``)
        when the env var is unset — engaging an unconfigured mechanism
        cannot have any effect because the call-site short-circuits.
        """
        if self.config is None or not _mechanism_is_configured(self.config, name):
            return False
        self.activation.engage_mechanism(name)
        return True

    def disengage_mechanism(self, name: MechanismName) -> bool:
        """Disengage and return True iff the mechanism is currently engaged.

        Returns False if the mechanism was already inactive (no audit-
        worthy state change occurred).
        """
        if self.config is None or not _mechanism_is_configured(self.config, name):
            return False
        was_active = self.activation.is_active(name)
        self.activation.disengage_mechanism(name)
        return was_active


def _mechanism_is_configured(
    config: HighTrafficSessionConfig,
    name: MechanismName,
) -> bool:
    """Map mechanism name to its env-var-derived field on the frozen config."""
    if name == "batching":
        return config.batch_cadence_s is not None
    if name == "convergence_override":
        return config.convergence_threshold_override is not None
    if name == "observer_downgrade":
        return config.observer_downgrade is not None
    msg = f"Unknown mechanism name: {name!r}"
    raise ValueError(msg)


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
