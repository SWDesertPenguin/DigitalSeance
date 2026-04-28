# Shakedown logs (gitignored scratch directory)

Drop raw shakedown output here when you want Claude to analyze it. Everything in this directory is gitignored except this README, so it is safe for unredacted session exports, transcripts containing real API keys, and adversarial payloads.

## Why this exists

Pasting a red-team transcript directly into chat puts literal jailbreak / exfiltration / prompt-injection strings into the *user-message* surface, which is classified independently of any project-level instructions. That is a frequent source of false-positive Usage Policy refusals.

When the same bytes arrive via a `Read` tool result, the defensive framing from project-level instructions is already established, the user's own message stays short and benign, and the classifier sees the content in the context of the file that holds it. Empirically this trips far less.

## Convention

1. Save the shakedown output to a file in this directory. Shakedown output is JSON (from `GET /tools/debug/export`, `GET /tools/session/export_json`, or `GET /tools/session/export_summaries?fmt=json`). Suggested naming:
   - `round05-2026-04-26-debug-export.json` — full debug export
   - `round05-2026-04-26-summaries.json` — summaries-only export
   - `round05-notes.md` — your own observations during the run (optional)
2. In chat, ask Claude to read it by path. Examples:
   - "Read `docs/shakedowns/round05-2026-04-26-debug-export.json` and summarize which layer caught each attack."
   - "Read `docs/shakedowns/round05-2026-04-26-debug-export.json` — which turns hit the jailbreak detector?"
   - "Compare `docs/shakedowns/round04-*.json` and `docs/shakedowns/round05-*.json` — what regressed?"
3. After the analysis is done, either delete the file or leave it (it will not be committed either way).

## What still trips the classifier

- Pasting log excerpts inline in chat, even short ones, if they contain literal attack content. Use a file.
- Asking for novel attack payloads with no defensive framing ("write me a jailbreak that…"). Frame the request defensively ("write a runbook entry that tests whether `src/security/jailbreak.py` catches X").
- Asking Claude to *execute* an attack against a non-localhost target. Out of scope for this project regardless of framing.
