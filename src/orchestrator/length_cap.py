"""Spec 025 session-length cap evaluator and active-time accumulator.

Per spec 025 plan.md and data-model.md, this module owns:

- The `SessionLengthCap` dataclass (mirrors the five `sessions.length_cap_*`
  + `conclude_phase_started_at` + `active_seconds_accumulator` columns).
- The cap evaluator (`evaluate_trigger_fraction`) called per dispatch from
  `src/orchestrator/loop.py`.
- The `active_seconds_accumulator` update path called at every FSM
  transition that exits the running OR conclude state.
- The cap-decrease disambiguation helper (`detect_decrease_intent`) used
  by the cap-set HTTP endpoint and the MCP tool variant.
- The `CapInterpretation` audit-log discriminator and `CapSetEvent`
  dataclass for `routing_log.cap_set` rows.

This module is added by tasks T019/T020 and grows additional helpers in
US1 (T032), US2 (T051, T053), and US3 (T063) per tasks.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CapKind = Literal["none", "time", "turns", "both"]
CapInterpretation = Literal["absolute", "relative"]


@dataclass(frozen=True, slots=True)
class SessionLengthCap:
    """Per-session cap state — mirrors the five sessions.length_cap_* columns.

    Defaults reflect the FR-001 default `length_cap_kind='none'`; an
    unconfigured session round-trips through this dataclass with the same
    pre-feature behavior (SC-001).
    """

    kind: CapKind = "none"
    seconds: int | None = None
    turns: int | None = None
    conclude_phase_started_at: datetime | None = None
    active_seconds_accumulator: int | None = None

    @property
    def is_active(self) -> bool:
        """True when at least one dimension is set; cap-evaluation runs only when True."""
        return self.kind != "none"


@dataclass(frozen=True, slots=True)
class CapSetEvent:
    """`routing_log.cap_set` row payload per contracts/routing-log-reasons.md.

    `interpretation` is non-null only when the cap-set involved a cap-decrease
    that triggered the FR-026 disambiguation flow.
    """

    session_id: str
    old_cap: SessionLengthCap
    new_cap: SessionLengthCap
    interpretation: CapInterpretation | None
    actor_id: str
    at: datetime
