# SPDX-License-Identifier: AGPL-3.0-or-later

"""Action-label registry for audit-log viewer (spec 029 FR-006 / FR-014 / FR-015).

Public surface (per `specs/029-audit-log-viewer/contracts/shared-module-contracts.md` §1):

- ``LABELS``: ``dict[str, dict[str, Any]]`` mapping audit action strings to
  registry entries. Each entry has a ``label`` (required ``str``) and an
  optional ``scrub_value`` (``bool``, default ``False``) that signals the
  FR-001 endpoint and FR-010 broadcast helper to replace ``previous_value`` /
  ``new_value`` with the literal string ``"[scrubbed]"`` before transmission.
- ``format_label(action)``: returns the registered label, or the
  ``"[unregistered: <action>]"`` fallback (FR-015). Emits a WARN log on the
  unregistered path.
- ``is_scrub_value(action)``: returns ``True`` when the action's entry has
  ``scrub_value=True``; ``False`` otherwise (including unregistered actions).

Direct callers MUST NOT iterate ``LABELS`` from outside this module unless
they are the parity gate (``scripts/check_audit_label_parity.py``) or the
architectural test (``tests/test_029_architectural.py``). Adding new actions
is additive; removing an action is a breaking contract change.

The frontend mirror (``frontend/audit_labels.js``) carries the same keys and
``label`` strings; the parity gate fails the build on drift.
"""

from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger(__name__)


# Initial v1 seed per research.md §9. Each entry mirrors a known
# ``append_audit_event(action=...)`` call site in the codebase. New audit
# actions added by downstream specs (022, 024, ...) MUST add an entry here
# AND the matching frontend mirror in the same PR; the CI parity gate
# enforces.
LABELS: dict[str, dict[str, Any]] = {
    "add_participant": {"label": "Facilitator added participant"},
    "approve_participant": {"label": "Facilitator approved participant"},
    "reject_participant": {"label": "Facilitator rejected participant"},
    "remove_participant": {"label": "Facilitator removed participant"},
    "pause_loop": {"label": "Facilitator paused the loop"},
    "resume_loop": {"label": "Facilitator resumed the loop"},
    "start_loop": {"label": "Facilitator started the loop"},
    "stop_loop": {"label": "Facilitator stopped the loop"},
    "transfer_facilitator": {"label": "Facilitator role transferred"},
    "set_routing_preference": {"label": "Routing preference changed"},
    "set_budget": {"label": "Budget changed"},
    "review_gate_approve": {"label": "Review gate: draft approved"},
    "review_gate_reject": {"label": "Review gate: draft rejected"},
    "review_gate_edit": {"label": "Review gate: draft edited"},
    "review_gate_pause_scope_changed": {
        "label": "Review-gate pause scope changed",
    },
    "rotate_token": {"label": "Auth token rotated", "scrub_value": True},
    "revoke_token": {"label": "Auth token revoked", "scrub_value": True},
    "cap_set": {"label": "Session length cap changed"},
    "auto_pause_on_cap": {
        "label": "Loop auto-paused (length cap reached)",
    },
    "manual_stop_during_conclude": {
        "label": "Loop manually stopped during conclude phase",
    },
    "session_config_change": {"label": "Session config changed"},
    # Spec 022 disposition-transition + re-surface actions (Session 2026-05-11).
    "detection_event_acknowledged": {"label": "Detection event acknowledged"},
    "detection_event_dismissed": {"label": "Detection event dismissed"},
    "detection_event_auto_resolved": {"label": "Detection event auto-resolved"},
    "detection_event_resurface": {"label": "Detection event re-surfaced"},
}


def format_label(action: str) -> str:
    """Return the registered label for ``action``, or the fallback marker.

    Unregistered actions render as ``"[unregistered: <action>]"`` per
    spec FR-015 and emit a WARN log so operators can detect registry drift
    (research.md §10).
    """
    entry = LABELS.get(action)
    if entry is None:
        _logger.warning(
            "audit_label_drift action=%s",
            action,
        )
        return f"[unregistered: {action}]"
    return str(entry["label"])


def is_scrub_value(action: str) -> bool:
    """Return True when the entry for ``action`` carries ``scrub_value=True``.

    Unregistered actions return ``False`` (no scrubbing applied).
    """
    entry = LABELS.get(action)
    if entry is None:
        return False
    return bool(entry.get("scrub_value", False))
