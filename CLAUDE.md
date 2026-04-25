# SACP Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-23

## Active Technologies
- Python 3.11+ (constitution §6.1) + FastAPI, asyncpg, Alembic, cryptography (Fernet), bcrypt (001-core-data-model)
- PostgreSQL 16 via Docker Compose (001-core-data-model)
- bcrypt, IP binding, token expiry (002-participant-auth)
- litellm>=1.83.0, 8-mode routing, circuit breaker (003-turn-loop-engine)
- sentence-transformers, numpy — SafeTensors only (004-convergence-cadence)
- Structured JSON summarization via cheapest model (005-summarization-checkpoints)
- FastAPI SSE server, ~47 MCP endpoints, port 8750 (006-mcp-server)
- 7-layer security pipeline — sanitization, spotlighting, validation, exfiltration, jailbreak, prompt defense, log scrubbing (007-ai-security-pipeline)
- 4-tier delta system prompts with canary tokens (008-prompts-security-wiring)
- Per-participant rate limiting, 60 req/min default (009-rate-limiting)
- Review-gate pause scope (session / participant) configurable at create + mid-session (010)
- Web UI: FastAPI app on port 8751, WebSocket /ws/{session_id} with v1 event envelope, single-file React SPA via CDN + SRI pins, HttpOnly+Secure+SameSite=Strict signed cookies (011-web-ui)

## Project Structure

```text
src/
  api_bridge/       # LiteLLM provider dispatch
  auth/             # AuthService, guards
  database/         # asyncpg pooling, Fernet encryption
  models/           # Frozen dataclasses
  repositories/     # 8 data access objects (append-only)
  orchestrator/     # Turn loop, routing, context, convergence, cadence
  security/         # 7 security modules
  prompts/          # 4-tier delta system prompt assembly
  mcp_server/       # FastAPI + 25 endpoints + rate limiter
tests/
alembic/
specs/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.11+ (constitution §6.1): Follow standard conventions

## Recent Changes
- Drop per-message speaker prefix (2026-04-25) — PR #124's `[Name (kind)] ` per-line prefix in `_secure_content` was observed in shakedown causing Gemini 2.5-flash-lite to (a) copy other speakers' content verbatim as if impersonating them and (b) auto-prefix its own responses with the same format. Less-robust models read the bracket prefix as a chat-app role marker. Reverting `_secure_content` to the pre-PR-#124 body (`<sacp:type>cleaned`) — the `[Participants]` roster still delivers human-vs-AI typing without giving smaller models a per-line pattern to mimic. Haiku and gpt-4o-mini handled the prefix correctly so no regression for them. `_speaker_label` deleted; `roster` param kept on signatures for now (cleanup deferred).
- Gemini default → `gemini-2.5-flash-lite` (2026-04-25) — Google moved free-tier `generateContent` quota off the 2.0 family; new keys hit `limit: 0` on `gemini-2.0-flash` / `gemini-2.0-flash-lite`. Confirmed via direct ListModels + per-model `:generateContent` test on a fresh key — 2.5-flash-lite, 2.5-flash, 3.1-flash-lite-preview, flash-lite-latest, and Gemma all have quota; both 2.0 variants 429. PROVIDER_DEFAULTS for `gemini` now points at `gemini/gemini-2.5-flash-lite` (1M context, low tier).
- API-key prefix warning (2026-04-25) — `AddParticipantDialog` and `ResetAICredentialsDialog` now show a soft inline warning under the API key field when the pasted key's prefix doesn't match the selected provider (`openai` → `sk-` not `sk-ant-`, `anthropic` → `sk-ant-`, `gemini` → `AIza`, `groq` → `gsk_`). Surfaced after a shakedown sent an `sk-ant-` key to OpenAI's endpoint and got a confusing 401 instead of an upfront signal. Warning only — self-hosted gateways may legitimately use arbitrary tokens, so submit isn't blocked.
- Post-shakedown polish (2026-04-25) — three UX fixes. (1) Speaker labels in exports — `/tools/debug/export`, `/tools/session/export_markdown`, and `/tools/session/export_json` now embed `speaker_display_name` next to `speaker_id` so transcripts are self-contained. (2) Error toasts — reducer dedupes identical errors + caps at 5; `ErrorToasts` auto-fades each toast after 10s; dismiss button enlarged. Fixes "can't close provider_unreachable toast" when a misconfigured AI keeps re-emitting. (3) Departed-AI section — offline/removed/reset participants now collapse under a "Departed (N)" `<details>` in both ParticipantList and BudgetPanel. BudgetCard hides edit when status is departed.
- Loop resilience + reset-empty-model guard (2026-04-25) — three small fixes from the Gemini-quota shakedown. (1) `_run_loop` no longer breaks on `AllParticipantsExhaustedError` — sleeps with backoff and retries instead, so adding an AI mid-session (after a Reset → Release → Add cycle) is picked up automatically. (2) `_ResetAICredentialsBody` rejects empty/whitespace `provider`/`model`/`api_endpoint` swaps via `field_validator`, preventing the COALESCE-overwrites-with-empty-string bug observed when an operator cleared the model field. (3) `_broadcast_provider_error` log line no longer double-prefixes (`gemini/gemini/gemini-2.0-flash` → `gemini/gemini-2.0-flash`).
- AI awareness sweep (2026-04-24, PR #124) — three coordinated changes so AIs can tell humans apart and signal back. (A1) Prompt assembler injects a `[Participants]` roster (`name (human)` / `name (AI:provider)`) and prefixes every transcript message with the speaker's labeled name. (A2) New `src/orchestrator/signals.py` heuristics surface open AI questions via `ai_question_opened` WS events; rendered in a new `AIQuestionsPanel` (resolved client-side). (A3) Refusal/exit phrases (`I'm stepping back`, `this conversation is over`, etc.) emit `ai_exit_requested`; ParticipantCard shows a yellow banner with "Honor (→ observer)" and "Dismiss" actions. All detection is heuristic + advisory — no AI is auto-muted.
- Summary history + export (2026-04-24, PR #123) — new `GET /tools/session/list_summaries` returns chronological checkpoints; `GET /tools/session/export_summaries?fmt=json|markdown` produces a digest. `SummaryPanel` gains lazy-loaded "Earlier checkpoints" `<details>` + Export .md / Export .json buttons (Blob download).
- Providers (2026-04-24, PR #122) — Gemini and Groq added to the sponsor `_AddAIBody` provider whitelist + Web UI dialogs. Defaults: `gemini/gemini-2.0-flash` (1M ctx) and `groq/llama-3.3-70b-versatile` (128k ctx). LiteLLM handles dispatch with no provider-specific branching.
- Drop provider+model dedupe (2026-04-24, PR #121) — `_reject_duplicate_ai` (facilitator) and `_reject_duplicate_ai_in_session` (sponsor) deleted. Two AIs of the same model under different API keys is a legitimate config; display_name uniqueness alone is sufficient to prevent UI ambiguity.
- Reset AI (2026-04-23, PR #120) — new `POST /tools/facilitator/reset_ai_credentials` (in-place API key rotation) and `POST /tools/facilitator/release_ai_slot` (soft unbind, status='reset' frees the display name for re-add). Both sponsor-capable via `_require_facilitator_or_inviter`. Dedupe guards (`_reject_duplicate_display_name`, `_reject_duplicate_human_name`) widened to skip `offline`/`reset` so re-add under the same name no longer 409s. UI: ↻ reset + ⏏ release buttons on AI ParticipantCards, `ResetAICredentialsDialog` modal, `status-reset` cards dim with "released" badge. Humans (provider='human') rejected with 400.
- Test08 sweep (2026-04-23) — `_InjectMessageBody.content` and `_EditDraftBody.edited_content` capped at 64 KB via Pydantic `max_length`; `_RejectDraftBody.reason` capped at 2 KB. Runbook annotated with Test08 pass/fail for all 18+ tested sections (only §3.1 failed). UX finding §X.1: facilitator note leaked into AI transcript via review_gate_edit.
- Test06-Web07 sweep (2026-04-23, PR #112) — review_gate one-shot auto-revert after draft resolve (ConversationLoop._prior_routing cache), remove_participant cascades to sponsored AIs via invited_by, pending user sees "Request declined" + 4s redirect; red-team runbook 5.4 annotated with gpt-4o-mini fiction-wrapper FAIL
- Test06-Web06 sweep (2026-04-22, PR #110) — summary feedback loop closed (speaker-type filter + watermark to max source_turn), participant_removed event for reject refresh, hourly-only budget cap renders correctly
- Test06-Web05 sweep (2026-04-22, PR #108) — archive auto-summary runs before status flip, summarize_now per-session lock, addressed_only routing matches @name or name as word
- Test06-Web04 sweep (2026-04-22, PR #106) — re-login after logout (cookie carries token, /me no longer rotates), budget 0 = no cap, currency formatting, Summarize-now + Review-gate-all + Archive-confirm controls, session ID visible
- Test06-Web03 sweep (2026-04-22, PR #105) — rotate_my_token cascade fix, sponsor perms for budget/routing, revoke boot-out, display-name dedupe 409s, facilitator prefix swap on transfer
- Session-restore + transfer broadcasts (PR #103) — cookie F5 restore, transfer_facilitator broadcasts both sides, Show-my-token
- docs/red-team-runbook.md — 70+ attacks keyed to the 7-layer security pipeline
- 011-web-ui: Phase 2 COMPLETE (2026-04-20) — 10 user stories shipped on port 8751, React SPA with CDN+SRI, strict CSP, HttpOnly cookie auth, WebSocket v1 event envelope
- Phase 1 COMPLETE (2026-04-20) — all scenario tests pass after PR #84
- 010 review-gate pause scope — facilitator-configurable session/participant pause, dispatch-pause while drafts pending
- 009-rate-limiting: Per-participant rate limiting middleware
- 008-prompts-security-wiring: 4-tier delta prompts + security pipeline wiring
- 007-ai-security-pipeline: Defense-in-depth security layer (7 modules)


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
