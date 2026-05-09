# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end tests for MCP server endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from src.mcp_server.app import _add_middleware, _attach_services, _include_routers
from tests.conftest import TEST_ENCRYPTION_KEY


def _build_test_app(pool: asyncpg.Pool) -> FastAPI:
    """Build a FastAPI app with test services (no lifespan)."""
    app = FastAPI(title="SACP Test")
    _add_middleware(app)
    _include_routers(app)
    _attach_services(app, pool, TEST_ENCRYPTION_KEY)
    return app


@pytest.fixture
async def client(
    pool: asyncpg.Pool,
) -> AsyncGenerator[tuple[httpx.AsyncClient, FastAPI], None]:
    """Provide an async HTTP client backed by the test app."""
    app = _build_test_app(pool)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as c:
        yield c, app


_SESSION_BODY = {
    "name": "E2E Test Session",
    "display_name": "Facilitator",
    "provider": "openai",
    "model": "gpt-4o",
    "model_tier": "high",
    "model_family": "gpt",
    "context_window": 128000,
    "api_key": "test-api-key",
}

_PARTICIPANT_BODY = {
    "display_name": "AI Speaker",
    "provider": "openai",
    "model": "gpt-4o-mini",  # distinct from facilitator's gpt-4o to clear dedupe check
    "model_tier": "mid",
    "model_family": "gpt",
    "context_window": 128000,
    "api_key": "test-participant-key",
}


async def _create_session(client: httpx.AsyncClient) -> dict:
    """Create a session and return the response JSON."""
    resp = await client.post("/tools/session/create", json=_SESSION_BODY)
    assert resp.status_code == 200
    return resp.json()


async def _add_participant(
    client: httpx.AsyncClient,
    token: str,
) -> dict:
    """Add a participant and return the response JSON."""
    resp = await client.post(
        "/tools/facilitator/add_participant",
        json=_PARTICIPANT_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.json()


async def test_create_session(client):
    """POST /tools/session/create returns session_id and auth_token."""
    c, _ = client
    data = await _create_session(c)
    assert "session_id" in data
    assert "facilitator_id" in data
    assert "branch_id" in data
    assert "auth_token" in data


async def test_create_session_with_explicit_name_persists(client):
    """An explicit ``name`` in the body is stored verbatim and echoed back."""
    c, _ = client
    body = {**_SESSION_BODY, "name": "Round08-quantum"}
    resp = await c.post("/tools/session/create", json=body)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Round08-quantum"


async def test_create_session_with_blank_name_auto_generates(client):
    """A blank ``name`` falls through to the adjective-animal-hex slug."""
    c, _ = client
    body = {**_SESSION_BODY, "name": ""}
    resp = await c.post("/tools/session/create", json=body)
    assert resp.status_code == 200
    name = resp.json()["name"]
    assert name and name != ""
    parts = name.split("-")
    assert len(parts) == 3
    assert all(parts), "auto-generated slug should have three non-empty segments"


async def test_add_participant_with_auth(client):
    """POST /tools/facilitator/add_participant requires auth."""
    c, _ = client
    session = await _create_session(c)
    data = await _add_participant(c, session["auth_token"])
    assert "participant_id" in data
    assert "auth_token" in data
    assert data["role"] == "participant"


async def test_inject_message(client):
    """POST /tools/participant/inject_message enqueues successfully."""
    c, _ = client
    session = await _create_session(c)
    participant = await _add_participant(c, session["auth_token"])
    resp = await c.post(
        "/tools/participant/inject_message",
        json={"content": "Hello from human", "priority": 1},
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "enqueued"


async def test_full_flow_to_history(client, mock_litellm):
    """Full flow: create → add participant → execute turn → get history."""
    c, app = client
    session = await _create_session(c)
    participant = await _add_participant(c, session["auth_token"])
    loop = app.state.conversation_loop
    await loop.execute_turn(session["session_id"])
    resp = await c.get(
        "/tools/participant/history",
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 1
    assert any("Test AI response" in m["content"] for m in messages)


async def test_inject_persists_to_transcript_immediately(client):
    """inject_message writes to the transcript at enqueue time, not deferred.

    Regression: interjections used to be persisted by the loop's
    _persist_interjections on the next turn, which meant they got a
    turn_number AFTER any AI turn that was in-flight when they arrived.
    """
    c, _ = client
    session = await _create_session(c)
    participant = await _add_participant(c, session["auth_token"])
    await c.post(
        "/tools/participant/inject_message",
        json={"content": "First question", "priority": 1},
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    resp = await c.get(
        "/tools/participant/history",
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    messages = resp.json()["messages"]
    humans = [m for m in messages if m["type"] == "human"]
    assert len(humans) == 1
    assert humans[0]["content"] == "First question"


async def test_inject_ordering_relative_to_ai_turn(client, mock_litellm):
    """Interjection injected after an AI turn gets a later turn_number."""
    c, app = client
    session = await _create_session(c)
    participant = await _add_participant(c, session["auth_token"])
    loop = app.state.conversation_loop
    await loop.execute_turn(session["session_id"])
    await c.post(
        "/tools/participant/inject_message",
        json={"content": "Follow-up", "priority": 1},
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    resp = await c.get(
        "/tools/participant/history",
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    messages = resp.json()["messages"]
    ai_turn = next(m["turn"] for m in messages if m["type"] == "ai")
    human_turn = next(m["turn"] for m in messages if m["content"] == "Follow-up")
    assert human_turn > ai_turn


async def test_debug_export_as_facilitator(client):
    """Facilitator can dump everything about a session."""
    c, _ = client
    session = await _create_session(c)
    participant = await _add_participant(c, session["auth_token"])
    await c.post(
        "/tools/participant/inject_message",
        json={"content": "hello", "priority": 1},
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    resp = await c.get(
        f"/tools/debug/export?session_id={session['session_id']}",
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 200
    dump = resp.json()
    assert dump["session"]["id"] == session["session_id"]
    assert len(dump["participants"]) >= 2
    assert all("auth_token_hash" not in p for p in dump["participants"])
    assert "config_snapshot" in dump
    assert len(dump["interrupts"]) == 1


async def test_debug_export_rejects_non_facilitator(client):
    """Participants (non-facilitator) cannot call /tools/debug/export."""
    c, _ = client
    session = await _create_session(c)
    participant = await _add_participant(c, session["auth_token"])
    resp = await c.get(
        f"/tools/debug/export?session_id={session['session_id']}",
        headers={"Authorization": f"Bearer {participant['auth_token']}"},
    )
    assert resp.status_code == 403


async def test_add_participant_rejects_placeholder(client):
    """Swagger default 'string' is rejected at the edge, not forwarded."""
    c, _ = client
    session = await _create_session(c)
    resp = await c.post(
        "/tools/facilitator/add_participant",
        json={**_PARTICIPANT_BODY, "model": "string"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 422


async def test_add_participant_allows_same_model_different_name(client):
    """Two AIs with the same provider+model coexist as long as display_names differ.

    Use case: same model under two different API keys (different accounts,
    different cost buckets, different role personas). The display_name
    dedupe alone is enough to prevent UI ambiguity; the prior provider+model
    409 was too aggressive and blocked legitimate multi-account configs.
    """
    c, _ = client
    session = await _create_session(c)
    first = await c.post(
        "/tools/facilitator/add_participant",
        json=_PARTICIPANT_BODY,
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert first.status_code == 200
    second = await c.post(
        "/tools/facilitator/add_participant",
        json={**_PARTICIPANT_BODY, "display_name": "AI Speaker Twin", "api_key": "different-key"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert second.status_code == 200
    assert second.json()["participant_id"] != first.json()["participant_id"]


async def test_add_participant_still_rejects_duplicate_display_name(client):
    """Display-name dedupe is still enforced — that's the only ambiguity check left."""
    c, _ = client
    session = await _create_session(c)
    first = await c.post(
        "/tools/facilitator/add_participant",
        json=_PARTICIPANT_BODY,
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert first.status_code == 200
    second = await c.post(
        "/tools/facilitator/add_participant",
        json=_PARTICIPANT_BODY,
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert second.status_code == 409
    assert "already in this session" in second.json().get("detail", "")


async def test_start_loop_refuses_without_human_message(client):
    """start_loop returns 409 when no human message exists yet."""
    c, _ = client
    session = await _create_session(c)
    resp = await c.post(
        "/tools/session/start_loop",
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 409
    assert "opening message" in resp.json().get("detail", "").lower()


async def test_session_rename(client):
    """set_name updates the session name and rejects blanks."""
    c, _ = client
    session = await _create_session(c)
    ok = await c.post(
        "/tools/session/set_name",
        json={"name": "Renamed By Test"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert ok.status_code == 200
    assert ok.json()["name"] == "Renamed By Test"
    blank = await c.post(
        "/tools/session/set_name",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert blank.status_code == 422


async def test_unauthenticated_returns_error(client):
    """Endpoints requiring auth return 401 without a token."""
    c, _ = client
    resp = await c.get("/tools/participant/history")
    assert resp.status_code == 401


async def test_list_summaries_returns_empty_initially(client):
    """list_summaries returns an empty list before any checkpoint runs."""
    c, _ = client
    session = await _create_session(c)
    resp = await c.get(
        "/tools/session/list_summaries",
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"summaries": []}


async def test_export_summaries_markdown_empty(client):
    """export_summaries with no checkpoints returns the empty-state marker."""
    c, _ = client
    session = await _create_session(c)
    resp = await c.get(
        "/tools/session/export_summaries?fmt=markdown",
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "markdown"
    assert "_No summaries yet._" in body["content"]


async def test_export_summaries_json_empty(client):
    """export_summaries default format is JSON; empty session yields '[]'."""
    c, _ = client
    session = await _create_session(c)
    resp = await c.get(
        "/tools/session/export_summaries",
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["format"] == "json"
    assert body["content"].strip() == "[]"


async def test_reset_ai_credentials_rotates_key_in_place(client):
    """Facilitator can rotate an AI's API key without losing the row."""
    c, _ = client
    session = await _create_session(c)
    ai = await _add_participant(c, session["auth_token"])
    resp = await c.post(
        "/tools/facilitator/reset_ai_credentials",
        json={"participant_id": ai["participant_id"], "api_key": "sk-rotated-42"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reset"


async def test_reset_ai_credentials_no_key_required_for_ollama(client):
    """Ollama doesn't auth — reset must accept a missing api_key."""
    c, _ = client
    session = await _create_session(c)
    add_resp = await c.post(
        "/tools/facilitator/add_participant",
        json={
            "display_name": "Llama Local",
            "provider": "ollama",
            "model": "ollama_chat/llama3.2:3b",
            "model_tier": "low",
            "model_family": "llama",
            "context_window": 4096,
            "api_key": "",
            "api_endpoint": "http://192.168.1.10:11434",
        },
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert add_resp.status_code == 200
    pid = add_resp.json()["participant_id"]
    resp = await c.post(
        "/tools/facilitator/reset_ai_credentials",
        json={"participant_id": pid, "api_endpoint": "http://192.168.1.20:11434"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reset"


async def test_reset_ai_credentials_requires_key_for_non_ollama(client):
    """Non-ollama providers still require an api_key — 422 when omitted."""
    c, _ = client
    session = await _create_session(c)
    ai = await _add_participant(c, session["auth_token"])
    resp = await c.post(
        "/tools/facilitator/reset_ai_credentials",
        json={"participant_id": ai["participant_id"]},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 422
    assert "api_key" in resp.text.lower()


async def test_reset_ai_credentials_rejects_human_target(client):
    """Humans have no credentials — reset must 400."""
    c, _ = client
    session = await _create_session(c)
    # Add a human participant via the facilitator path (default provider='human').
    human_resp = await c.post(
        "/tools/facilitator/add_participant",
        json={"display_name": "Human Bob"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert human_resp.status_code == 200
    human_id = human_resp.json()["participant_id"]
    resp = await c.post(
        "/tools/facilitator/reset_ai_credentials",
        json={"participant_id": human_id, "api_key": "irrelevant"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert resp.status_code == 400


async def test_release_ai_slot_frees_display_name(client):
    """After release, re-adding the same display_name succeeds (no 409)."""
    c, _ = client
    session = await _create_session(c)
    ai = await _add_participant(c, session["auth_token"])
    # Release the AI's slot.
    released = await c.post(
        "/tools/facilitator/release_ai_slot",
        json={"participant_id": ai["participant_id"], "reason": "key burned out"},
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert released.status_code == 200
    # Re-add under the same display_name + provider+model — must NOT 409.
    readd = await c.post(
        "/tools/facilitator/add_participant",
        json=_PARTICIPANT_BODY,
        headers={"Authorization": f"Bearer {session['auth_token']}"},
    )
    assert readd.status_code == 200
    assert readd.json()["participant_id"] != ai["participant_id"]


async def _add_human_and_get_token(client, fac_token, display_name):
    """Add a human participant via the facilitator; return their token."""
    resp = await client.post(
        "/tools/facilitator/add_participant",
        json={"display_name": display_name},
        headers={"Authorization": f"Bearer {fac_token}"},
    )
    assert resp.status_code == 200
    return resp.json()["auth_token"]


async def _sponsor_adds_ai(client, sponsor_token):
    """Sponsor adds an AI via /tools/participant/add_ai; return participant_id."""
    resp = await client.post(
        "/tools/participant/add_ai",
        json={
            "display_name": "Sponsored AI",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "model_tier": "mid",
            "model_family": "gpt",
            "context_window": 128000,
            "api_key": "sk-sponsor-key",
        },
        headers={"Authorization": f"Bearer {sponsor_token}"},
    )
    assert resp.status_code == 200
    return resp.json()["participant_id"]


async def test_reset_ai_credentials_sponsor_allowed(client):
    """Sponsor (invited_by) can reset their own AI; a third party cannot."""
    c, _ = client
    session = await _create_session(c)
    sponsor_token = await _add_human_and_get_token(c, session["auth_token"], "Sponsor Human")
    ai_id = await _sponsor_adds_ai(c, sponsor_token)
    ok = await c.post(
        "/tools/facilitator/reset_ai_credentials",
        json={"participant_id": ai_id, "api_key": "sk-sponsor-rotated"},
        headers={"Authorization": f"Bearer {sponsor_token}"},
    )
    assert ok.status_code == 200
    other_token = await _add_human_and_get_token(c, session["auth_token"], "Third Party")
    denied = await c.post(
        "/tools/facilitator/reset_ai_credentials",
        json={"participant_id": ai_id, "api_key": "sk-hijack"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert denied.status_code == 403
