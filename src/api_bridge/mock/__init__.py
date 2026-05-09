"""Mock provider adapter package (spec 020).

Deterministic fixture-driven dispatch with no network access.
`MockAdapter` registers with `AdapterRegistry` under the name `"mock"`
at module-import time per research.md §4.
"""

from __future__ import annotations

from src.api_bridge.adapter import AdapterRegistry
from src.api_bridge.mock.adapter import MockAdapter

AdapterRegistry.register("mock", MockAdapter)
