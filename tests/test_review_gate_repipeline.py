# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 012 FR-006 / Constitution §4.9 approach (b) — review-gate re-pipeline.

Verifies that approve_draft and edit_draft:
  1. Run the security pipeline before persisting.
  2. Return 422 when content re-flags and no override_reason is supplied.
  3. Log a facilitator_override security_events row and persist when content
     re-flags and override_reason is supplied.
  4. Persist without an override row when the pipeline passes on re-run.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.participant_api.tools.facilitator import _repipeline_or_raise

_PATCH = "src.participant_api.tools.facilitator.run_security_pipeline"

# ---------------------------------------------------------------------------
# Fake pipeline outputs
# ---------------------------------------------------------------------------


def _make_validation(*, blocked: bool, risk: float = 0.0, findings: list | None = None):
    return SimpleNamespace(
        blocked=blocked,
        risk_score=risk,
        findings=frozenset(findings or []),
    )


def _clean_pipeline(content: str):
    """Simulate a pipeline that always passes."""
    return _make_validation(blocked=False), content, [], 1, 1


def _blocking_pipeline(content: str):
    """Simulate a pipeline that always blocks."""
    return _make_validation(blocked=True, risk=0.9, findings=["override_phrase"]), content, [], 1, 1


# ---------------------------------------------------------------------------
# Fake request / participant
# ---------------------------------------------------------------------------


def _make_request(log_repo=None):
    state = SimpleNamespace(log_repo=log_repo or AsyncMock())
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _make_participant(pid="fac-1"):
    return SimpleNamespace(id=pid)


def _make_draft(sid="ses-1", turn=5):
    return SimpleNamespace(session_id=sid, turn_number=turn)


# ---------------------------------------------------------------------------
# _repipeline_or_raise unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_passes_returns_cleaned_content() -> None:
    """If the re-pipeline passes, return the cleaned content — no 422, no override row."""
    log_repo = AsyncMock()
    request = _make_request(log_repo)
    participant = _make_participant()
    draft = _make_draft()

    with patch(_PATCH, side_effect=_clean_pipeline):
        result = await _repipeline_or_raise(request, participant, "clean content", draft, None)

    assert result == "clean content"
    log_repo.log_security_event.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_flags_no_reason_raises_422() -> None:
    """Re-flagged content + no override_reason → 422 Unprocessable Entity."""
    log_repo = AsyncMock()
    request = _make_request(log_repo)

    with (
        patch(_PATCH, side_effect=_blocking_pipeline),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _repipeline_or_raise(
            request, _make_participant(), "flagged content", _make_draft(), None
        )

    assert exc_info.value.status_code == 422
    assert "override_reason" in exc_info.value.detail
    log_repo.log_security_event.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_flags_with_reason_logs_override_and_returns_content() -> None:
    """Re-flagged content + override_reason → override row logged, original content returned."""
    log_repo = AsyncMock()
    request = _make_request(log_repo)
    participant = _make_participant("fac-99")
    draft = _make_draft("ses-42", turn=7)

    with patch(_PATCH, side_effect=_blocking_pipeline):
        result = await _repipeline_or_raise(
            request, participant, "flagged but justified", draft, "Operator confirmed safe"
        )

    assert result == "flagged but justified"
    log_repo.log_security_event.assert_awaited_once()
    call_kwargs = log_repo.log_security_event.call_args.kwargs
    assert call_kwargs["layer"] == "facilitator_override"
    assert call_kwargs["session_id"] == "ses-42"
    assert call_kwargs["turn_number"] == 7
    assert call_kwargs["override_reason"] == "Operator confirmed safe"
    assert call_kwargs["override_actor_id"] == "fac-99"
    assert call_kwargs["blocked"] is False
    findings = json.loads(call_kwargs["findings"])
    assert "override_phrase" in findings


@pytest.mark.asyncio
async def test_pipeline_passes_cleaning_is_used() -> None:
    """When pipeline passes, the cleaned (sanitized) content is returned, not the raw input."""
    log_repo = AsyncMock()
    request = _make_request(log_repo)

    def sanitizing_pipeline(content: str):
        cleaned = content.replace("UNSAFE", "REDACTED")
        return _make_validation(blocked=False), cleaned, [], 1, 1

    with patch(_PATCH, side_effect=sanitizing_pipeline):
        result = await _repipeline_or_raise(
            request, _make_participant(), "text with UNSAFE word", _make_draft(), None
        )

    assert result == "text with REDACTED word"
    log_repo.log_security_event.assert_not_called()


# ---------------------------------------------------------------------------
# run_security_pipeline public export
# ---------------------------------------------------------------------------


def test_run_security_pipeline_is_importable() -> None:
    """Spec 012 FR-006: run_security_pipeline is public so facilitator can import it."""
    from src.orchestrator.loop import run_security_pipeline

    assert callable(run_security_pipeline)


def test_run_security_pipeline_returns_5_tuple() -> None:
    """run_security_pipeline returns (validation, cleaned, exfil_flags, v_ms, e_ms)."""
    from src.orchestrator.loop import run_security_pipeline

    result = run_security_pipeline("hello world")
    assert len(result) == 5
    _validation, cleaned, exfil_flags, v_ms, e_ms = result
    assert isinstance(cleaned, str)
    assert isinstance(exfil_flags, list)
    assert isinstance(v_ms, int)
    assert isinstance(e_ms, int)
