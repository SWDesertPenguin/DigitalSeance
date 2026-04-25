"""Unit tests for add_participant request validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_server.tools.facilitator import _AddParticipantBody, _EditDraftBody
from src.mcp_server.tools.participant import (
    MAX_MESSAGE_CONTENT_CHARS,
    _AddAIBody,
    _InjectMessageBody,
)


def _valid_body(**overrides) -> dict:
    body = {
        "display_name": "AI Speaker",
        "provider": "ollama",
        "model": "llama3.2:3b",
        "model_tier": "low",
        "model_family": "llama",
        "context_window": 8192,
    }
    body.update(overrides)
    return body


def test_accepts_well_formed_body():
    model = _AddParticipantBody(**_valid_body())
    assert model.model == "llama3.2:3b"


@pytest.mark.parametrize(
    "field",
    ["display_name", "provider", "model", "model_tier", "model_family"],
)
def test_rejects_swagger_placeholder(field):
    with pytest.raises(ValidationError):
        _AddParticipantBody(**_valid_body(**{field: "string"}))


@pytest.mark.parametrize(
    "field",
    ["display_name", "provider", "model", "model_tier", "model_family"],
)
def test_rejects_blank(field):
    with pytest.raises(ValidationError):
        _AddParticipantBody(**_valid_body(**{field: "   "}))


def test_rejects_placeholder_case_insensitive():
    with pytest.raises(ValidationError):
        _AddParticipantBody(**_valid_body(model="STRING"))


def test_strips_whitespace():
    model = _AddParticipantBody(**_valid_body(model="  llama3.2:3b  "))
    assert model.model == "llama3.2:3b"


# --- Oversized-message guards (red-team runbook 3.1) --------------------------


def test_inject_message_accepts_at_cap():
    body = _InjectMessageBody(content="A" * MAX_MESSAGE_CONTENT_CHARS)
    assert len(body.content) == MAX_MESSAGE_CONTENT_CHARS


def test_inject_message_rejects_over_cap():
    with pytest.raises(ValidationError):
        _InjectMessageBody(content="A" * (MAX_MESSAGE_CONTENT_CHARS + 1))


def test_inject_message_rejects_empty():
    with pytest.raises(ValidationError):
        _InjectMessageBody(content="")


def test_inject_message_rejects_multi_megabyte_payload():
    with pytest.raises(ValidationError):
        _InjectMessageBody(content="Test data" * 250_000)


def test_edit_draft_rejects_over_cap():
    with pytest.raises(ValidationError):
        _EditDraftBody(
            draft_id="d1",
            edited_content="A" * (MAX_MESSAGE_CONTENT_CHARS + 1),
        )


# --- Sponsor add_ai provider whitelist ----------------------------------------


def _valid_ai_body(**overrides) -> dict:
    body = {
        "display_name": "Sponsored",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "model_tier": "mid",
        "model_family": "claude",
        "context_window": 200_000,
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize("provider", ["anthropic", "openai", "ollama", "gemini", "groq"])
def test_add_ai_accepts_whitelisted_providers(provider):
    body = _AddAIBody(**_valid_ai_body(provider=provider))
    assert body.provider == provider


def test_add_ai_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        _AddAIBody(**_valid_ai_body(provider="bedrock"))
