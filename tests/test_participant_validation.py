"""Unit tests for add_participant request validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_server.tools.facilitator import _AddParticipantBody


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
