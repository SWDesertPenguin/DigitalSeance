"""Per-session batch scheduler (spec 013 mechanism 1 / US1).

Hosts ``BatchEnvelope`` and the per-session flush task that coalesces
AI-to-human messages on the configured cadence. Spawned in the
``loop.py`` session-init path when ``HighTrafficSessionConfig.batch_cadence_s``
is set.
"""

from __future__ import annotations
