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
    "model": "gpt-4o",
    "model_tier": "high",
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


async def test_unauthenticated_returns_error(client):
    """Endpoints requiring auth return 401 without a token."""
    c, _ = client
    resp = await c.get("/tools/participant/history")
    assert resp.status_code == 401
