# SPDX-License-Identifier: AGPL-3.0-or-later

"""Facilitator scratch surface (spec 024).

This package is the operator-private workspace state surface. The
FR-001 architectural test (tests/test_024_architectural.py) enforces
that no code in src/orchestrator/, src/prompts/, src/api_bridge/, or
src/operations/ imports any symbol from this package — notes are NOT
part of the AI context-assembly pipeline.
"""

from __future__ import annotations
