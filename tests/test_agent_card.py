# SPDX-License-Identifier: AGPL-3.0-or-later

"""Agent Card endpoint tests — A2A discovery surface for the orchestrator."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.participant_api.agent_card import agent_card_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(agent_card_router)
    return app


def _get_body() -> dict:
    return TestClient(_make_app()).get("/.well-known/agent-card.json").json()


def test_well_formed_response() -> None:
    """200 OK with application/json content-type."""
    resp = TestClient(_make_app()).get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


def test_a2a_required_top_level_fields_present() -> None:
    """All AgentCard fields marked REQUIRED in the A2A proto are populated."""
    body = _get_body()
    required = (
        "name",
        "description",
        "version",
        "supportedInterfaces",
        "capabilities",
        "defaultInputModes",
        "defaultOutputModes",
        "skills",
    )
    for field in required:
        assert field in body, f"missing required AgentCard field: {field}"
        assert body[field], f"required field is empty: {field}"


def test_supported_interface_required_fields() -> None:
    """Each AgentInterface entry must carry url, protocolBinding, protocolVersion."""
    body = _get_body()
    interfaces = body["supportedInterfaces"]
    assert len(interfaces) >= 1
    iface = interfaces[0]
    for field in ("url", "protocolBinding", "protocolVersion"):
        assert field in iface, f"missing AgentInterface field: {field}"
    assert iface["protocolBinding"] in ("HTTP+JSON", "JSONRPC", "GRPC")


def test_capabilities_match_prompt_contract() -> None:
    """streaming=true (SSE turn-event broadcast), pushNotifications=false."""
    caps = _get_body()["capabilities"]
    assert caps["streaming"] is True
    assert caps["pushNotifications"] is False


def test_bearer_security_scheme() -> None:
    """HTTPAuth scheme=Bearer is declared and required via top-level security."""
    body = _get_body()
    bearer = body["securitySchemes"]["bearer"]["httpAuthSecurityScheme"]
    assert bearer["scheme"] == "Bearer"
    assert body["security"] == [{"bearer": []}]


def test_skills_cover_list_and_get_session_state() -> None:
    """In-scope skills are advertised with all AgentSkill REQUIRED fields."""
    body = _get_body()
    skill_ids = {skill["id"] for skill in body["skills"]}
    assert {"list_sessions", "get_session_state"} <= skill_ids
    for skill in body["skills"]:
        for required in ("id", "name", "description", "tags"):
            assert required in skill, f"skill missing required field: {required}"
        assert isinstance(skill["tags"], list) and skill["tags"]


def test_provider_required_fields() -> None:
    """AgentProvider organization + url are populated."""
    provider = _get_body()["provider"]
    assert provider["organization"]
    assert provider["url"].startswith("https://")


def test_disambiguation_in_description() -> None:
    """Description contains the four-collision disambiguation note."""
    desc = _get_body()["description"]
    assert "four" in desc.lower()
    for collision in ("Symposium", "MatiasIac", "Snapmaker", "IETF"):
        assert collision in desc, f"missing collision reference: {collision}"


def test_cache_control_header_set() -> None:
    """Cache-Control max-age=3600 per A2A §8.6.1."""
    resp = TestClient(_make_app()).get("/.well-known/agent-card.json")
    cache_control = resp.headers.get("cache-control", "")
    assert "max-age=3600" in cache_control


def test_no_secrets_in_response_body() -> None:
    """No credentials, tokens, or internal hostnames bleed into the card."""
    body = _get_body()
    serialized = repr(body).lower()
    forbidden = ("api_key", "apikey=", "password", "sk_live", "sk_test", "eyj")
    for token in forbidden:
        assert token not in serialized, f"forbidden marker leaked: {token}"


def test_service_endpoint_derived_from_request() -> None:
    """AgentInterface.url tracks the request base URL (no hard-coded host)."""
    client = TestClient(_make_app(), base_url="http://orchestrator.example:8750")
    body = client.get("/.well-known/agent-card.json").json()
    # Equality, not startswith — py/incomplete-url-substring-sanitization treats
    # substring URL checks as a broken-allowlist shape; equality also tighter.
    assert body["supportedInterfaces"][0]["url"] == "http://orchestrator.example:8750"


def test_default_modes_are_json_compatible() -> None:
    """default*Modes are media-type strings; JSON is in both input and output."""
    body = _get_body()
    assert "application/json" in body["defaultInputModes"]
    assert "application/json" in body["defaultOutputModes"]


def test_card_is_json_serializable() -> None:
    """The whole response must be a valid JSON document (no Python-only types)."""
    import json

    raw = TestClient(_make_app()).get("/.well-known/agent-card.json").text
    parsed = json.loads(raw)
    assert parsed["name"] == "Sovereign AI Collaboration Protocol Orchestrator"
