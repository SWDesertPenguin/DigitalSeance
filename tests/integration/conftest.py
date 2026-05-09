# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration-tier conftest — auto-mark every test in this directory.

Tests under `tests/integration/` are automatically tagged with
`@pytest.mark.integration` so they run in the slow CI tier
(`pytest -m integration`). New files don't need to remember the marker
per-test; landing in this directory is sufficient.

See `docs/cross-spec-integration.md` for tier shape, runtime budget,
and the boundary catalogue.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-mark every test in tests/integration/ with @pytest.mark.integration."""
    del config
    for item in items:
        # Only mark tests that live under tests/integration/.
        if "tests/integration" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
