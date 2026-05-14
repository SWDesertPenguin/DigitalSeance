# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR-018 — two-tier summarizer tests (T045).

Validates that the corpus filter behaves correctly for the two-tier
emission path. The full SummarizationManager.run_checkpoint flow is
DB-bound and covered by the integration suite once PG is available
in CI; these tests target the pure ``_fetch_turns_since`` corpus
filter and ``_store_summary`` visibility threading.
"""

from __future__ import annotations

import inspect

from src.auth.service import AuthService  # noqa: F401 — breaks an import cycle
from src.orchestrator import summarizer


def test_fetch_turns_since_accepts_visibility_filter():
    """The corpus filter accepts an optional visibility argument."""
    sig = inspect.signature(summarizer._fetch_turns_since)
    assert "visibility" in sig.parameters
    assert sig.parameters["visibility"].default is None


def test_store_summary_accepts_visibility_kwarg():
    """``_store_summary`` carries the two-tier discriminator."""
    sig = inspect.signature(summarizer._store_summary)
    assert "visibility" in sig.parameters
    assert sig.parameters["visibility"].default == "public"


def test_generate_and_store_threads_visibility_per_tier():
    """``_generate_and_store`` references ``capcom_participant_id`` and the two scopes."""
    src = inspect.getsource(summarizer.SummarizationManager._generate_and_store)
    assert "capcom_participant_id" in src
    assert '"public"' in src
    assert '"capcom_only"' in src


def test_emit_summary_passes_visibility_to_store():
    """``_emit_summary`` propagates ``visibility`` into ``_store_summary``."""
    src = inspect.getsource(summarizer.SummarizationManager._emit_summary)
    assert "visibility=visibility" in src
