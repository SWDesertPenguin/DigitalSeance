"""Observer-downgrade evaluator (spec 013 mechanism 3 / US3).

Hosts the per-turn priority computation, downgrade decision, and audit
row writers. Wired into the turn-prep phase of ``loop.py`` only when
``HighTrafficSessionConfig.observer_downgrade is not None``.
"""

from __future__ import annotations
