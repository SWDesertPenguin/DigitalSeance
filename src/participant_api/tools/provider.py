# SPDX-License-Identifier: AGPL-3.0-or-later

"""Provider introspection endpoints.

Surfaces ``POST /tools/provider/list_models`` so the AddAI / Reset
dialogs can show a dropdown of currently-available models for the
operator's API key. Avoids the foot-gun where someone types a model
string by hand and gets a 429 / 404 from the provider because that
specific model lost its quota or was deprecated.

Auth: any authenticated participant. Sponsors need this just as much
as facilitators (both can add AIs).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api_bridge.list_models import (
    ListModelsError,
    list_provider_models,
)
from src.models.participant import Participant
from src.participant_api.middleware import get_current_participant

router = APIRouter(prefix="/tools/provider", tags=["provider"])


class _ListModelsBody(BaseModel):
    """Request body for live model listing."""

    provider: Literal["anthropic", "openai", "gemini", "groq", "ollama"]
    api_key: str = Field(default="", max_length=4096)
    api_endpoint: str | None = Field(default=None, max_length=2048)


@router.post("/list_models")
async def list_models(
    request: Request,
    body: _ListModelsBody,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return the current chat-model catalog for ``provider`` + ``api_key``.

    Pending participants (auto-issued bearer before facilitator approval)
    are blocked because the Ollama branch issues server-side outbound
    requests to operator-controlled hosts — that's not a flow that
    should be reachable before approval.
    """
    del request  # auth dependency only
    if participant.role == "pending":
        raise HTTPException(403, "Pending participants cannot list provider models")
    try:
        models = await list_provider_models(
            provider=body.provider,
            api_key=body.api_key,
            api_endpoint=body.api_endpoint,
        )
    except ListModelsError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    return {
        "provider": body.provider,
        "models": [{"model": m.model, "display": m.display} for m in models],
    }
