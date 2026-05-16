# SPDX-License-Identifier: AGPL-3.0-or-later

"""/.well-known/agent-card.json — A2A discovery for the SACP orchestrator.

Publishes a static Agent Card at the RFC 8615 well-known path defined
in A2A spec §8 so A2A-aware clients can discover the orchestrator. The
card describes orchestrator-level identity, capabilities, and skills;
session state never flows into the response. Per-participant Agent
Cards are deferred until Phase 4 human-participant identity work lands.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

agent_card_router = APIRouter(tags=["a2a-discovery"])

_ORCHESTRATOR_NAME = "Sovereign AI Collaboration Protocol Orchestrator"
_ORCHESTRATOR_VERSION = "0.1.0"
_A2A_PROTOCOL_VERSION = "0.3"
_PROVIDER_ORG = "Sovereign AI Collaboration Protocol Project"
_PROVIDER_URL = "https://github.com/SWDesertPenguin/DigitalSeance"
_DOCS_URL = "https://github.com/SWDesertPenguin/DigitalSeance"
_CACHE_MAX_AGE_SECONDS = 3600

_DESCRIPTION = (
    "Orchestrator for Sovereign AI Collaboration Protocol sessions: multi-AI "
    "conversation with per-participant bring-your-own-API-key cost attribution "
    "and per-participant context isolation. Acronym disambiguation: SACP here "
    "is the Sovereign AI Collaboration Protocol orchestrator, not Symposium-dev "
    "SACP, MatiasIac SACP, the IETF Simple Agent Communication Protocol draft, "
    "or Snapmaker SACP (four other unrelated projects share the SACP acronym)."
)

_PROVIDER: dict[str, str] = {
    "organization": _PROVIDER_ORG,
    "url": _PROVIDER_URL,
}

_CAPABILITIES: dict[str, bool] = {
    "streaming": True,
    "pushNotifications": False,
}

_SECURITY_SCHEMES: dict[str, dict[str, object]] = {
    "bearer": {
        "httpAuthSecurityScheme": {
            "scheme": "Bearer",
            "description": (
                "Phase 1 static bearer token authenticates the caller. "
                "Phase 4 will migrate to OAuth 2.1 per spec 030."
            ),
        },
    },
}

_SECURITY_REQUIREMENTS: list[dict[str, list[str]]] = [{"bearer": []}]

_DEFAULT_INPUT_MODES: list[str] = ["application/json"]
_DEFAULT_OUTPUT_MODES: list[str] = ["application/json", "text/event-stream"]

_SKILLS: list[dict[str, object]] = [
    {
        "id": "list_sessions",
        "name": "List Sessions",
        "description": (
            "Enumerate collaboration sessions the caller's bearer token can "
            "observe. Returns session id, status, and participant count."
        ),
        "tags": ["session", "discovery"],
    },
    {
        "id": "get_session_state",
        "name": "Get Session State",
        "description": (
            "Return current routing state, participant roster, and recent "
            "events for one session the caller is authorized to observe."
        ),
        "tags": ["session", "state"],
    },
]


@agent_card_router.get("/.well-known/agent-card.json")
async def agent_card(request: Request) -> JSONResponse:
    """Return the A2A Agent Card for this orchestrator deployment.

    Cache-Control max-age=3600 per A2A §8.6.1 (Server Requirements).
    The card body is assembled from module constants plus the request
    base URL; no session state, credentials, or internal hostnames are
    leaked into the response.
    """
    base_url = str(request.base_url).rstrip("/")
    body = _build_card(base_url)
    return JSONResponse(
        status_code=200,
        content=body,
        headers={"Cache-Control": f"public, max-age={_CACHE_MAX_AGE_SECONDS}"},
    )


def _build_card(base_url: str) -> dict[str, object]:
    """Assemble the full Agent Card dict per A2A §8.3 (AgentCard object)."""
    return {
        "name": _ORCHESTRATOR_NAME,
        "description": _DESCRIPTION,
        "version": _ORCHESTRATOR_VERSION,
        "supportedInterfaces": [_build_interface(base_url)],
        "provider": _PROVIDER,
        "documentationUrl": _DOCS_URL,
        "capabilities": _CAPABILITIES,
        "securitySchemes": _SECURITY_SCHEMES,
        "security": _SECURITY_REQUIREMENTS,
        "defaultInputModes": _DEFAULT_INPUT_MODES,
        "defaultOutputModes": _DEFAULT_OUTPUT_MODES,
        "skills": _SKILLS,
    }


def _build_interface(base_url: str) -> dict[str, str]:
    """Return one AgentInterface entry rooted at the caller-visible base URL."""
    return {
        "url": base_url,
        "protocolBinding": "HTTP+JSON",
        "protocolVersion": _A2A_PROTOCOL_VERSION,
    }
