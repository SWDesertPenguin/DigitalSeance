# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 — inject_message visibility default + invariant checks (T014).

Validation-layer tests on ``_InjectMessageBody`` and the visibility
resolver. DB-free.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.participant_api.tools.participant import (
    _enforce_capcom_only_invariants,
    _InjectMessageBody,
    _resolve_inject_visibility,
)


def _human():
    p = MagicMock()
    p.id = "h1"
    p.session_id = "s1"
    p.provider = "human"
    p.role = "participant"
    return p


def _panel_ai():
    p = MagicMock()
    p.id = "ai-panel"
    p.session_id = "s1"
    p.provider = "openai"
    p.role = "participant"
    return p


def _capcom_ai(pid="ai-capcom"):
    p = MagicMock()
    p.id = pid
    p.session_id = "s1"
    p.provider = "openai"
    p.role = "participant"
    return p


def _session(capcom_id: str | None):
    s = MagicMock()
    s.capcom_participant_id = capcom_id
    return s


def _request_with_capcom(capcom_id: str | None):
    req = MagicMock()
    req.app.state.session_repo.get_session = AsyncMock(return_value=_session(capcom_id))
    return req


def test_body_accepts_public_visibility():
    body = _InjectMessageBody(content="hi", visibility="public")
    assert body.visibility == "public"


def test_body_accepts_capcom_only_visibility():
    body = _InjectMessageBody(content="hi", visibility="capcom_only")
    assert body.visibility == "capcom_only"


def test_body_rejects_unknown_visibility():
    with pytest.raises(ValidationError):
        _InjectMessageBody(content="hi", visibility="private")


def test_body_visibility_defaults_to_none():
    body = _InjectMessageBody(content="hi")
    assert body.visibility is None


@pytest.mark.asyncio
async def test_visibility_default_public_when_capcom_unassigned():
    body = _InjectMessageBody(content="hi")
    out = await _resolve_inject_visibility(
        _request_with_capcom(None),
        _human(),
        body,
    )
    assert out == "public"


@pytest.mark.asyncio
async def test_visibility_default_public_when_env_var_false():
    body = _InjectMessageBody(content="hi")
    os.environ.pop("SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN", None)
    out = await _resolve_inject_visibility(
        _request_with_capcom("c1"),
        _human(),
        body,
    )
    assert out == "public"


@pytest.mark.asyncio
async def test_visibility_default_capcom_only_when_env_var_true(monkeypatch):
    body = _InjectMessageBody(content="hi")
    monkeypatch.setenv("SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN", "true")
    out = await _resolve_inject_visibility(
        _request_with_capcom("c1"),
        _human(),
        body,
    )
    assert out == "capcom_only"


@pytest.mark.asyncio
async def test_explicit_public_overrides_default(monkeypatch):
    monkeypatch.setenv("SACP_CAPCOM_DEFAULT_ON_HUMAN_JOIN", "true")
    body = _InjectMessageBody(content="hi", visibility="public")
    out = await _resolve_inject_visibility(
        _request_with_capcom("c1"),
        _human(),
        body,
    )
    assert out == "public"


def test_invariants_reject_capcom_only_without_capcom():
    """INV-3 — capcom_only is unavailable when no CAPCOM is assigned."""
    with pytest.raises(HTTPException) as exc:
        _enforce_capcom_only_invariants(_human(), capcom_id=None)
    assert exc.value.status_code == 409


def test_invariants_reject_panel_ai_capcom_only():
    """INV-4 — panel AI participants cannot emit capcom_only."""
    with pytest.raises(HTTPException) as exc:
        _enforce_capcom_only_invariants(_panel_ai(), capcom_id="ai-capcom")
    assert exc.value.status_code == 422


def test_invariants_allow_capcom_ai_capcom_only():
    """The active CAPCOM AI can emit capcom_only."""
    capcom = _capcom_ai("ai-capcom")
    _enforce_capcom_only_invariants(capcom, capcom_id="ai-capcom")


def test_invariants_allow_human_capcom_only():
    """Humans can emit capcom_only when a CAPCOM is assigned."""
    _enforce_capcom_only_invariants(_human(), capcom_id="ai-capcom")
