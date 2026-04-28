# SACP Web UI — User Guide (DRAFT / WIP)

> **Status: DRAFT.** This guide covers the Phase 2 Web UI as of 2026-04-22. Features and screens may change. Report friction or gaps to the operator; this doc is meant to evolve with shakedown feedback.

SACP is a multi-party AI-and-human conversation tool. Multiple AIs and humans share a single transcript, take turns speaking, and can make decisions together via proposals. This guide shows you how to use the Web UI.

---

## 1. Getting in

Open the Web UI URL the operator gave you. You'll land on a page with four options:

- **Sign in with a token** — you already have a bearer token (e.g. issued when you created or joined a previous session).
- **Create a new session** — you want to be the facilitator of a new conversation.
- **Request to join a session** — someone gave you a session ID and you're asking for access.
- **Redeem an invite code** — someone gave you an invite code that pre-approves you.

Pick the one that matches how you're starting.

### 1.1 Create a session (facilitator path)

1. Click **Create a new session**.
2. Enter your name. The system will store you as `Facilitator-<your name>`.
3. Click **Create session**.
4. You'll see a **token reveal** screen. **This is your API key. Copy it now and save it somewhere safe.** You'll need it for:
   - Logging back in on another browser
   - API / MCP / Swagger use
   - Anything beyond the Web UI
5. Click **I saved it — enter the session** to go to the session view.

The session gets an automatic name like `amber-otter-a3f1`. You can rename it anytime by clicking the name in the header.

### 1.2 Request to join

1. Click **Request to join a session**.
2. Enter the session ID (facilitator will give you this) and your display name.
3. Click **Request to join**.
4. You'll see a "Waiting for approval" screen showing the session name and other humans already in. You can't interact until the facilitator approves.
5. When approved, the screen automatically transitions into the full session view.
6. If the facilitator rejects, you'll be signed out.

### 1.3 Redeem an invite

1. Click **Redeem an invite code**.
2. Paste the invite code and your display name.
3. Click **Redeem**. Unlike Request-to-join, redeeming an invite skips the approval wait — you're in immediately.

### 1.4 Sign in with an existing token

1. Click **Sign in with a token**.
2. Paste the bearer token you saved when you first created or joined.
3. Click **Sign in**.

---

## 2. The session view at a glance

```
┌────────────────────────────────────────────────────────────────────┐
│  session-name [status] [loop: running]        Turn 5    ⬇md ⬇json │
├────────────┬──────────────────────────────────┬────────────────────┤
│  YOU       │                                  │  REVIEW GATE      │
│  - name    │       transcript scrolls here    │  - pending drafts │
│  - routing │                                  │                    │
│  [Show my  │                                  │  BUDGET           │
│   token]   │                                  │  - $spent/$cap     │
│            │                                  │                    │
│  PARTICIPS │                                  │  CONVERGENCE      │
│  Active    │                                  │  - sparkline       │
│    Alice   │                                  │                    │
│    AI-Bot  │                                  │  SUMMARY           │
│  Paused    │                                  │                    │
│    Llama   │                                  │  PROPOSALS         │
│  Pending   │                                  │  + open votes      │
│    Carol   │                                  │  + Resolved (N)    │
│            │                                  │                    │
│  [Start] [Stop] [Pause] [Resume] [Archive]    │                    │
│  [+ Add participant / Add my AI]              │                    │
│                                               │                    │
│  ADMIN (facilitator only) ▸                   │                    │
├────────────┴──────────────────────────────────┴────────────────────┤
│  Type here — Ctrl+Enter to send                         [Send]   │
└────────────────────────────────────────────────────────────────────┘
```

### 2.1 Header

- **Session name** — click to rename (facilitator only).
- **Status badge** — `active` / `paused` / `archived`.
- **Loop badge** — `running` means AIs are being dispatched; `idle` means the turn loop is stopped.
- **Turn N** — current turn counter.
- **⬇ md / ⬇ json** — export the full transcript.
- **🌙 / ☀** — toggle light/dark theme.
- **Connection dot** — green = WebSocket connected; yellow = reconnecting; red = disconnected.

### 2.2 Left sidebar

- **You** — your own name/role/provider/budget + routing preference + **Show my token** button (rotates and reveals your bearer; prior copies become invalid).
- **Participants** — active / paused / pending sections. Each card shows name, role, provider/model, "added by X" attribution for AIs, and a health badge.
  - Facilitators get a red ✕ to remove participants and a routing-preference dropdown per participant.
- **Session controls** (facilitator only) — Start/Stop/Pause/Resume the turn loop, Archive the session.
- **+ Add participant** (facilitator) or **+ Add my AI** (participant) — opens the add dialog.
- **Admin** (facilitator only) — collapsible panel with pending approvals, invite generation, session config, facilitator transfer, and audit log.

### 2.3 Center

- **Transcript** — messages in chronological order. Scrolls on new turns.
- **Message input** — type and press Ctrl+Enter (or click Send). Pinned to the viewport bottom.

### 2.4 Right sidebar

- **Review gate** — shows AI draft responses waiting for approval (only when an AI's routing preference is `review_gate`).
- **Budget** — per-AI spend vs. daily cap (if set). Facilitators get an **edit** link to adjust caps.
- **Convergence** — sparkline of how similar the recent AI responses have become. A horizontal line marks the divergence threshold.
- **Summary** — decisions, open questions, key positions, and narrative generated every 10 turns.
- **Proposals** — open votes + collapsible history of resolved proposals.

---

## 3. Running a session (facilitator)

### 3.1 Add participants

Click **+ Add participant** in the left sidebar.

- **Humans** — pick `human` provider. They'll need a token (see §3.6 for how to share it).
- **AIs** — pick `anthropic` / `openai` / `ollama`. The form auto-fills sensible model defaults:
  - `anthropic` → `claude-haiku-4-5-20251001`
  - `openai` → `gpt-4o-mini`
  - `ollama` → `ollama_chat/llama3.2:3b`
- Paste an API key for Anthropic / OpenAI / Gemini / Groq. Ollama runs locally so it doesn't need a key — but the SACP container must be able to reach the Ollama host (see §3.1.1).
- Dedup: a session can't have two AIs with the same display name. Two AIs with the same `provider + model` under different keys are allowed (PR #121).

### 3.1.1 Adding an Ollama participant

Ollama runs on the host (or LAN), not inside the SACP container. Two prerequisites:

**1. Bind Ollama to all interfaces** — set `OLLAMA_HOST=0.0.0.0:11434` before `ollama serve` (or `Environment="OLLAMA_HOST=0.0.0.0:11434"` in the systemd unit). Default `127.0.0.1` only accepts loopback connections.

**2. Use the host's LAN IP in the API endpoint field** — find it with `hostname -I` (Linux) or `ipconfig` (Windows), enter `http://<that-IP>:11434`. The placeholder text suggests this format.

`http://host.docker.internal:11434` works on Docker Desktop (Mac / Windows) where the alias is auto-injected, but is unreliable on Linux Docker and TrueNAS even with the `extra_hosts: ["host.docker.internal:host-gateway"]` mapping in [docker-compose.yml](../docker-compose.yml). Prefer the LAN IP form.

After both: AddParticipant → `provider=ollama` → fill in the API endpoint → click **Fetch models** to populate the dropdown from your installed tags.

### 3.2 Send the opening message

**The loop refuses to start without a human message first.** This prevents AIs from hallucinating a welcome. Type an opening prompt in the input box, Ctrl+Enter, then click **Start loop**.

### 3.3 Run, pause, stop

- **Start loop** — begins AI turn dispatching.
- **Pause** — pauses the session; AIs stop, humans can still post.
- **Resume** — returns from paused.
- **Stop loop** — halts dispatching without pausing the session.
- **Archive** — marks session archived (read-only). Irreversible for Phase 2; you can still export transcript.

### 3.4 Set budgets

In the Budget panel, click **edit** on any AI card. Enter hourly and/or daily $ caps. Leave blank for no cap. Caps auto-enforce: once exceeded, the AI gets skipped with reason `budget_exceeded`.

### 3.5 Review gate

Set any AI's routing preference to `review_gate` (via the dropdown on its participant card). From then on, the AI's responses are staged as drafts in the Review Gate panel instead of auto-posting. You choose:

- **Approve** — post as-is.
- **Edit** — open the text editor, rewrite, then save+approve.
- **Reject** — discard; the AI gets another chance next cycle.

You can also toggle the **pause scope** in the Review Gate header:
- `session-wide` — all AIs pause while any draft is pending.
- `participant` — only the AI whose draft is pending pauses; others keep talking.

### 3.6 Inviting people

Two paths:

**Invite code** (recommended for trusted participants):
1. Admin panel → Invite → set max uses → **Generate invite**.
2. Copy the code, share it securely.
3. Recipient uses **Redeem an invite code** on the landing page.

**Request-to-join** (for anyone with the session ID):
1. Share your session ID (shown in your copied token data or in `/tools/debug/export`).
2. They use **Request to join** and enter the session ID + their name.
3. You approve them from Admin → Pending approvals.

**Direct add** (facilitator creates them):
1. **+ Add participant** with provider = human.
2. You need to deliver the participant's bearer token to them (they'll use **Sign in with a token**). The backend returns the token in the add-participant response — copy it from the Swagger response or API call. *(UI surface for this pending — see the token-reveal improvements in feedback.)*

### 3.7 Proposals

Anyone can create a proposal. Proposals stay open until resolved.

- **Create** — click **+ New** on the Proposals panel. Topic + position.
- **Vote** — Accept / Reject / Abstain.
- **Resolve** — facilitator-only. Moves to the collapsed **Resolved (N)** history section with the final tally.

### 3.8 Transfer facilitator

Admin panel → **Transfer facilitator** → pick a participant → confirm.

- The target's UI immediately upgrades to facilitator.
- Your UI immediately downgrades to participant.
- Both sides happen live without a refresh.

### 3.9 Rename session

Click the session name in the header, edit, press Enter (or click away). Broadcasts to everyone.

### 3.10 Theme

Click the 🌙 / ☀ icon in the header to toggle light/dark.

### 3.11 Export

Click **⬇ .md** for a formatted markdown dump or **⬇ .json** for raw transcript JSON. Includes all messages, speakers, and timestamps.

---

## 4. Participating (non-facilitator)

### 4.1 Send a message

Type, Ctrl+Enter. Your own messages appear in the transcript immediately.

### 4.2 Add your own AI

Click **+ Add my AI**. The dialog opens with provider locked to AI choices (no "human" option). The AI is tagged "added by *your name*" on its card. If the AI fails to respond, check the facilitator — they can remove and you can re-add.

### 4.3 Change your routing preference

In the **You** panel, change the routing dropdown. Options:

| Preference | Behavior |
|---|---|
| `always` | Speak every opportunity |
| `review_gate` | Your drafts go to human approval |
| `delegate_low` | Delegate easy turns to a cheaper model |
| `domain_gated` | Only speak when topic matches your tags |
| `burst` | Speak every N turns |
| `observer` | Only speak when addressed |
| `addressed_only` | Only when someone @-mentions you |
| `human_only` | Only humans, never AIs, drive your turns |

### 4.4 Vote on proposals

Open proposals appear in the right sidebar. Click Accept / Reject / Abstain. You can only vote once per proposal.

### 4.5 Show your token

Click **Show my token** in the **You** panel to rotate and reveal a fresh bearer token. Use this if you need API/MCP access or want to sign in from another device. **Prior tokens are invalidated** — save the new one.

---

## 5. If things go wrong

### 5.1 "The UI says I'm disconnected"

- Check the connection dot (top right). Yellow = reconnecting (usually resolves within ~30s). Red = can't reach the server — check the container is up and the URL is right.
- If you see `4401` or `4403` close codes, your session expired. Sign back in.

### 5.2 "I refreshed the page and got kicked out"

This should no longer happen — the UI auto-restores from the cookie. If you *do* get kicked, your cookie may have expired (8-hour window) or been cleared by the browser.

### 5.3 "An AI isn't responding"

Check its participant card:
- `breaker-tripped (N)` badge → the AI failed N times in a row and is paused. Typical cause: bad API key, provider outage, or an Ollama host that can't be reached. Facilitator: remove and re-add after fixing the underlying cause.
- `budget_exceeded` → the AI hit its daily/hourly cap. Facilitator: raise the cap in the Budget panel, or wait for the window to reset.
- Just silent → it may be waiting its turn. Check the routing preferences — if only one AI is active and it just spoke, the loop backs off 5 → 10 → 20 → 40 → 60s until there's something new to say.

### 5.4 "My message didn't show up"

Your own messages appear immediately via WebSocket. If it's missing:
- Check the connection dot. If disconnected, the message may have failed to send.
- Hit Ctrl+Enter again — resending the same content is fine; the backend orders messages by arrival time.

### 5.5 "I can't see changes other facilitators made"

Most changes broadcast live. If you see stale state, click refresh — the cookie will restore your session and you'll get a fresh snapshot. Report what action wasn't reflecting, so the operator can log a bug.

### 5.6 "I got a 409 when I tried to start the loop"

You need to post at least one human message first. The system refuses to let AIs speak before a human has set the topic.

### 5.7 "I got a 422 when adding a participant"

A required field is empty or invalid (usually the API key on an AI). Check the form fields — the inline error below the submit button tells you which.

### 5.8 "The page won't load (stuck on 'Loading…')"

Browser issue or CSP is blocking a script. Check browser DevTools → Console. Share the errors with the operator.

---

## 6. Security notes

- **Never paste bearer tokens into chat** — they're API keys.
- **The facilitator can see everyone's cost totals.** Participants only see their own dollar amounts.
- **AI-generated output is sanitized** — scripts, raw HTML, dangerous link schemes, and tracking pixels are stripped automatically. Invisible Unicode characters are revealed with a warning badge.
- **The transcript is the source of truth** — if you said it, it's in the log (exported markdown/JSON, plus audit for facilitator actions).

---

## 7. Known limitations (Phase 2)

- **Single tab per token.** Opening the UI in a second tab invalidates the first tab's bearer (tokens rotate on refresh).
- **No in-session private chat between humans.** Everything any human types goes into the shared transcript visible to AIs. (Planned feature.)
- **Direct-add token delivery is manual.** Inviting someone by direct-add returns a token via API that the facilitator must copy out and hand over. Use the Invite code flow (§3.6) instead if possible.
- **Archived sessions are read-only forever.** No undelete.
- **No branching yet.** All messages are linear. (Phase 3.)
- **Ollama requires network configuration.** The SACP container must be able to reach the Ollama host. See operator docs.

---

## 8. Glossary

- **Facilitator** — the session owner. Can add/remove participants, approve/reject joiners, run the loop, set budgets, resolve proposals.
- **Participant** — anyone (human or AI) in the session who isn't the facilitator.
- **Turn loop** — the background job that decides which AI speaks next, dispatches the request, and persists the response.
- **Routing preference** — how aggressively an AI speaks (see §4.3).
- **Review gate** — an approval queue where AI drafts wait for human sign-off before posting.
- **Convergence** — a similarity score between recent AI responses. High = they're echoing each other. A **divergence prompt** nudges them to stake out different positions.
- **Summary / checkpoint** — every 10 turns, a structured recap is generated (decisions, questions, positions, narrative).
- **Proposal** — a decision item anyone can raise. Resolved by vote.
- **Breaker tripped** — an AI has failed 3 consecutive dispatches and is auto-paused.
- **Skip-spam backoff** — when the loop can't find anyone to dispatch to, it waits 5 → 10 → 20 → 40 → 60s between retries so it doesn't hammer the system.

---

## 9. Feedback

Spot something broken, unclear, or missing? Tell the operator. This guide is a DRAFT and needs real-session feedback to harden.
