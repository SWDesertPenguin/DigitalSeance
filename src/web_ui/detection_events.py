# SPDX-License-Identifier: AGPL-3.0-or-later

"""Event-class registry for the detection event history surface (spec 022).

Public surface (per ``data-model.md`` "Class-mapping registry" and
``research.md §5``):

- ``EVENT_CLASSES``: ``dict[str, dict[str, str]]`` mapping the five fixed
  panel-class keys to their display labels. Source of truth for the
  ``detection_events.event_class`` column values (also enforced via the
  alembic 017 CHECK constraint).
- ``format_class_label(class_key)``: returns the registered label, or the
  ``"[unregistered: <key>]"`` fallback. Emits a WARN log on the
  unregistered path.

The frontend mirror (``frontend/detection_event_taxonomy.js``) carries the
same keys + label strings; the parity gate at
``scripts/check_detection_taxonomy_parity.py`` enforces equality.

This module will gain the FR-001 / FR-006 endpoint handlers in Sweep 2.
The registry-only scope here makes the foundational phase test target
narrower and the parity gate simpler.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


# Fixed five-class v1 taxonomy per Clarifications §3 + §8. Adding a class
# requires updating BOTH this dict and the frontend mirror in the same PR,
# plus a spec amendment. The alembic 017 CHECK constraint on
# detection_events.event_class enforces the same set at the DB layer.
EVENT_CLASSES: dict[str, dict[str, str]] = {
    "ai_question_opened": {"label": "AI question opened"},
    "ai_exit_requested": {"label": "AI exit requested"},
    "density_anomaly": {"label": "Density anomaly"},
    "mode_recommendation": {"label": "Mode recommendation"},
    "mode_change": {"label": "Mode change"},
}


def format_class_label(class_key: str) -> str:
    """Return the registered label for ``class_key``, or fallback marker.

    Unregistered keys render as ``"[unregistered: <key>]"`` and emit a WARN
    log so operators can detect registry drift (mirrors spec 029's
    ``format_label`` fallback contract).
    """
    entry = EVENT_CLASSES.get(class_key)
    if entry is None:
        _logger.warning(
            "detection_events.unregistered_class_key",
            extra={"class_key": class_key},
        )
        return f"[unregistered: {class_key}]"
    return entry["label"]
