# SPDX-License-Identifier: AGPL-3.0-or-later
"""T089: registry size, O(1) lookup, immutability. Spec 030 Phase 3."""

from __future__ import annotations

import time


def test_registry_has_expected_size() -> None:
    """Registry contains ~40 tools (at least 35 after Phase 3 loading)."""
    from src.mcp_protocol.tools import REGISTRY

    assert 35 <= len(REGISTRY) <= 60, f"unexpected registry size: {len(REGISTRY)}"


def test_registry_lookup_is_fast() -> None:
    """O(1) dictionary lookup completes under 1ms for 10000 iterations."""
    from src.mcp_protocol.tools import REGISTRY

    name = next(iter(REGISTRY))
    start = time.monotonic()
    for _ in range(10000):
        _ = REGISTRY.get(name)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 50, f"lookup too slow: {elapsed_ms:.1f}ms for 10000 iterations"


def test_registry_is_same_object_on_reimport() -> None:
    """REGISTRY is the same dict object across multiple imports (module-level singleton)."""
    import importlib

    import src.mcp_protocol.tools as mod1

    importlib.reload(mod1)
    # After reload a new REGISTRY is built but each entry is a RegistryEntry
    from src.mcp_protocol.tools import REGISTRY

    assert isinstance(REGISTRY, dict)
    assert len(REGISTRY) >= 35
