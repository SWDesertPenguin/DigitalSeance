# SACP Testing & Validation Runbook

Step-by-step guide for testing the full conversation flow on a live deployment.

---

## Prerequisites

| Item | Value |
|------|-------|
| Server URL | `http://<HOST>:8750` |
| Swagger UI | `http://<HOST>:8750/docs` |
| Docker stack path | Wherever your Dockge/Compose stack lives |
| Required env vars | `SACP_DATABASE_URL`, `SACP_ENCRYPTION_KEY` |

You'll need at least one API key for an AI provider (Anthropic, OpenAI, or a running Ollama instance).

---

## 1. Clean Database Reset

Old sessions, participants, and interrupt queue entries persist across container rebuilds. Always start testing from a clean slate.

```bash
# Stop the stack
sudo docker compose down

# Remove the persistent data volume
sudo docker volume rm <stack>_pgdata

# Pull latest image
sudo docker pull ghcr.io/<owner>/<repo>:latest

# Start fresh — Alembic runs migrations on startup
sudo docker compose up -d
```

Verify the server is running:
```bash
curl http://<HOST>:8750/docs
```

---

## 2. Create a Session

No auth required. This creates the session, a facilitator participant, and the main conversation branch.

```bash
curl -X POST http://<HOST>:8750/tools/session/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Session",
    "display_name": "Facilitator",
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "model_tier": "high",
    "model_family": "claude",
    "context_window": 200000,
    "api_key": "<YOUR_ANTHROPIC_KEY>"
  }'
```

**Response:**
```json
{
  "session_id": "abc123",
  "facilitator_id": "fac456",
  "branch_id": "main-abc123",
  "status": "active",
  "auth_token": "<FACILITATOR_TOKEN>"
}
```

Save `auth_token` — you need it for all subsequent calls.

> **Keyless providers (Ollama):** Leave `api_key` as `""` or omit it. You still get an `auth_token` back.

---

## 3. Add AI Participants

Requires the facilitator's auth token. Add one or more AI participants.

### Add a Claude participant

```bash
curl -X POST http://<HOST>:8750/tools/facilitator/add_participant \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <FACILITATOR_TOKEN>" \
  -d '{
    "display_name": "Claude",
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "model_tier": "high",
    "model_family": "claude",
    "context_window": 200000,
    "api_key": "<YOUR_ANTHROPIC_KEY>"
  }'
```

### Add an Ollama/Llama participant

Uses the OpenAI-compatible API format that Ollama exposes. The `provider` is `openai` (tells LiteLLM which API format to use), NOT that you're calling OpenAI.

```bash
curl -X POST http://<HOST>:8750/tools/facilitator/add_participant \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <FACILITATOR_TOKEN>" \
  -d '{
    "display_name": "Llama",
    "provider": "openai",
    "model": "openai/llama3.2:3b",
    "model_tier": "low",
    "model_family": "llama",
    "context_window": 8192,
    "api_key": "not-needed",
    "api_endpoint": "http://<OLLAMA_HOST>:11434/v1"
  }'
```

**Response (both):**
```json
{
  "participant_id": "par789",
  "auth_token": "<PARTICIPANT_TOKEN>",
  "role": "participant"
}
```

Save each `participant_id` and `auth_token`.

> **Docker networking:** If Ollama runs in a separate container on the same Docker network, use the container hostname (e.g., `http://ix-ollama-ollama-1:11434/v1`). External IPs may not resolve from inside containers.

---

## 4. Inject a Conversation Topic

Seed the conversation before starting the loop. Use any participant's auth token.

```bash
curl -X POST http://<HOST>:8750/tools/participant/inject_message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ANY_PARTICIPANT_TOKEN>" \
  -d '{
    "content": "Discuss the ethical implications of autonomous AI decision-making in healthcare.",
    "priority": 1
  }'
```

**Response:**
```json
{
  "status": "enqueued",
  "id": 1
}
```

The injected message enters the interrupt queue and will be included in the next turn's context as a high-priority user message.

---

## 5. Start the Conversation Loop

Kicks off the async turn loop. The AI participants take turns responding.

```bash
curl -X POST http://<HOST>:8750/tools/session/start_loop \
  -H "Authorization: Bearer <FACILITATOR_TOKEN>"
```

**Response:**
```json
{
  "status": "started"
}
```

The loop runs continuously in the background. Each turn: pick next speaker (round-robin) -> assemble context -> dispatch to provider -> validate response -> persist.

---

## 6. Check History

View the conversation as it develops. Use any participant's auth token.

```bash
curl -X GET "http://<HOST>:8750/tools/participant/history?limit=10" \
  -H "Authorization: Bearer <ANY_PARTICIPANT_TOKEN>"
```

**Response:**
```json
{
  "messages": [
    {
      "turn": 1,
      "speaker": "par789",
      "type": "ai",
      "content": "The ethical implications of autonomous AI..."
    }
  ]
}
```

---

## 7. Inject More Messages Mid-Conversation

You can inject additional messages while the loop is running. They'll be picked up on the next turn.

```bash
curl -X POST http://<HOST>:8750/tools/participant/inject_message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ANY_PARTICIPANT_TOKEN>" \
  -d '{
    "content": "What about patient consent and data privacy?",
    "priority": 1
  }'
```

---

## 8. Stop the Loop

```bash
curl -X POST http://<HOST>:8750/tools/session/stop_loop \
  -H "Authorization: Bearer <FACILITATOR_TOKEN>"
```

**Response:**
```json
{
  "status": "stopped"
}
```

---

## 9. Export the Transcript

### Markdown format
```bash
curl -X GET http://<HOST>:8750/tools/session/export_markdown \
  -H "Authorization: Bearer <ANY_PARTICIPANT_TOKEN>"
```

### JSON format
```bash
curl -X GET http://<HOST>:8750/tools/session/export_json \
  -H "Authorization: Bearer <ANY_PARTICIPANT_TOKEN>"
```

---

## 10. Check Session Status

```bash
curl -X GET http://<HOST>:8750/tools/participant/status \
  -H "Authorization: Bearer <ANY_PARTICIPANT_TOKEN>"
```

---

## Operational Reference

### Provider Configuration Matrix

| Provider | `provider` field | `model` field | `api_key` | `api_endpoint` |
|----------|-----------------|---------------|-----------|----------------|
| Anthropic (Claude) | `anthropic` | `claude-sonnet-4-20250514` | Required | Leave empty |
| OpenAI (GPT) | `openai` | `gpt-4o` | Required | Leave empty |
| Ollama (local) | `openai` | `openai/<model_name>` | `not-needed` | `http://<host>:11434/v1` |

> Ollama uses `provider: openai` because it exposes an OpenAI-compatible API. LiteLLM uses this to determine the wire format. It does NOT call OpenAI.

### Database Reset (without full rebuild)

If you just want to clear data without rebuilding the container:

```bash
# Connect to the running postgres container
sudo docker exec -it <stack>-postgres-1 psql -U sacp -d sacp

# Truncate everything (respects FK order)
TRUNCATE votes, proposals, invites, review_gate_drafts,
  interrupt_queue, admin_audit_log, convergence_log,
  usage_log, routing_log, messages, branches CASCADE;
UPDATE sessions SET facilitator_id = NULL;
TRUNCATE participants CASCADE;
TRUNCATE sessions CASCADE;
```

### View Container Logs

```bash
# Application logs
sudo docker logs <stack>-sacp-1 --tail 50 -f

# Postgres logs
sudo docker logs <stack>-postgres-1 --tail 20
```

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| 403 on any endpoint | Missing or invalid Bearer token | Use the `auth_token` from session create or add_participant |
| 422 Unprocessable Entity | Missing required body fields | Check the request JSON matches the required fields |
| 500 on start_loop | Provider dispatch failure | Check container logs; verify API key and model name |
| Timeout on Ollama calls | LiteLLM async transport issue | Use `openai/` prefix with `/v1` endpoint instead of native `ollama/` prefix |
| AI ignores injected topic | Stale DB with old interrupts | Do a clean database reset before testing |
| No auth_token returned | Old image before auth fix | Pull latest GHCR image and rebuild |

### Useful Swagger UI Workflow

1. Open `http://<HOST>:8750/docs`
2. Call `POST /tools/session/create` — copy `auth_token` from response
3. Click **Authorize** button (top right) — paste `Bearer <token>`
4. All subsequent calls auto-include the auth header
5. Call `POST /tools/facilitator/add_participant` for each AI
6. Call `POST /tools/participant/inject_message` to seed topic
7. Call `POST /tools/session/start_loop`
8. Poll `GET /tools/participant/history` to watch the conversation
9. Call `POST /tools/session/stop_loop` when done
