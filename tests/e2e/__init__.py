# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 2 Web UI end-to-end tests — Playwright + a live SACP stack.

These tests require:
  * A running SACP backend (docker compose up -d) with both the MCP
    server on 8750 and the Web UI on 8751 reachable.
  * ``pip install "sacp[e2e]"`` or ``pip install pytest-playwright``.
  * ``playwright install chromium`` to fetch browser binaries.
  * ``SACP_RUN_E2E=1`` set in the environment (guards CI from
    accidentally picking them up without the infra).

Each test opens a real browser against the Web UI, so they run slower
than the unit suite. Use them for regression coverage of the acceptance
scenarios documented in ``specs/011-web-ui/spec.md``.
"""
