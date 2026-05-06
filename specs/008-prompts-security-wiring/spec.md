# Feature Specification: System Prompts & Security Wiring

**Feature Branch**: `008-prompts-security-wiring`
**Created**: 2026-04-12
**Status**: Draft
**Input**: "4-tier delta system prompts and security pipeline integration into turn loop and context assembly"

## Clarifications

### Session 2026-04-14

- Q: Default prompt_tier? → A: `mid` (core rules + collaboration guidelines, ~770 tokens)
- Q: Canary token format? → A: Multi-canary, random rare-string markers at 3 positions (start/mid/end), per-session unique, 16-char base32. No structural format (no HTML comment, no XML tag) so attackers have no pattern to evade.
- Canary hardening implemented in fix/canary-hardening (2026-04-14): `_generate_canaries()` uses `secrets.token_bytes(10)` + base32 encode. `_embed_canaries()` injects at start/mid/end of tier parts. `PromptProtector.check_leakage` checks all 3 via `canaries=` kwarg. Per-session storage of canaries for detection wiring is a future Phase 2 enhancement.
- FR-012 custom-prompt sanitize memoization implemented in fix/008-custom-prompt-memo (2026-05-05): `_sanitize_for_participant(participant_id, custom_prompt)` decorated with `functools.lru_cache(maxsize=1024)`; cache key matches the spec `(participant_id, custom_prompt_hash)` shape (lru_cache hashes args internally). `assemble_prompt` accepts an optional `participant_id` — when present (production turn-loop path via `_add_system_prompt`) sanitize is cached; when absent (tests, ad-hoc) the uncached `sanitize()` path is used. Invalidation is implicit: on participant_update the new (id, prompt) tuple misses the cache, the stale entry remains until LRU eviction; sanitize is pure so a stale entry never serves an incorrect value, only consumes memory.
- FR-011 tier-text memoization implemented in fix/008-tier-memoization (2026-05-05): `_tier_parts(prompt_tier)` decorated with `functools.lru_cache(maxsize=4)`. Cache key matches FR-011 (`prompt_tier`); 4-entry capacity matches the four tier values; invalidation is process-restart only (tier text is hardcoded). Canaries continue to rotate per-call — only the cumulative-delta parts list is cached, not the assembled output.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 4-Tier System Prompt Assembly (Priority: P1)

The system assembles a participant's system prompt from four delta tiers: low (~250 tokens, core rules), mid (~520 tokens, adds collaboration guidelines), high (~480 tokens, adds convergence awareness), max (~480 tokens, adds depth-over-brevity). Each tier builds on the previous. The participant's configured prompt_tier determines which tiers are included.

**Why this priority**: System prompts define how each AI behaves in the conversation. Without tiered prompts, all participants use raw custom prompts with no collaboration framing.

**Acceptance Scenarios**:

1. **Given** a participant with prompt_tier='low', **When** the prompt is assembled, **Then** only the core collaboration rules are included (~250 tokens).
2. **Given** a participant with prompt_tier='max', **When** the prompt is assembled, **Then** all four tiers are included (~1,730 tokens total).
3. **Given** a participant with a custom system_prompt, **When** the prompt is assembled, **Then** the custom prompt is appended after the tier content.

---

### User Story 2 - Security Pipeline in Context Assembly (Priority: P1)

The context assembler applies sanitization and spotlighting when building context. All messages are sanitized (injection patterns stripped). AI messages are additionally spotlighted (datamarked) before inclusion in another participant's context.

**Acceptance Scenarios**:

1. **Given** a message with ChatML tokens, **When** context is assembled, **Then** the tokens are stripped before inclusion.
2. **Given** an AI response being included in another AI's context, **When** context is assembled, **Then** it is datamarked with the source participant's ID.
3. **Given** a human interjection, **When** context is assembled, **Then** it is sanitized but NOT datamarked.

---

### User Story 3 - Security Pipeline in Turn Loop (Priority: P1)

After each AI response is received from the provider, the turn loop runs the output validation pipeline (injection check, exfiltration filter, jailbreak detection). High-risk responses are staged for review instead of entering the transcript.

**Acceptance Scenarios**:

1. **Given** an AI response containing injection markers, **When** output validation runs, **Then** the response is staged for facilitator review.
2. **Given** a clean AI response, **When** output validation runs, **Then** it is persisted normally.
3. **Given** an AI response with markdown image exfiltration, **When** the exfiltration filter runs, **Then** the images are stripped before persistence.

---

### Edge Cases

- What happens when all 4 tiers exceed a small model's context window? The MVC floor check in context assembly catches this — the participant is flagged as too-small for active participation. Hard contract: the assembled prompt fits if the participant's `context_window - max_tokens_per_turn - prompt_estimate > 0`; otherwise the participant is excluded from active dispatch.
- What happens when sanitization strips content that the spotlighting then tries to mark? Sanitization runs first, spotlighting runs on the cleaned content. Order is enforced in `_secure_content`.
- What happens when the participant has empty `custom_prompt` and an unrecognized `prompt_tier`? Per FR-001 default, tier falls back to `mid`; assembly proceeds with tier content + canaries only.
- What happens when tier text accidentally contains a 16-char base32 substring resembling a canary? The substring is plain prose, not a canary value, and the detection path (when wired) compares against the stored canary list — false-positive collision is impossible because comparison is exact-match against generated values, not pattern-shape.
- What happens when spotlight datamarks (`^<6-hex>^...`) appear in the same message as canary tokens (16-char base32)? They are distinct shapes (caret-delimited vs free-standing) and use disjoint detection pathways; collision is not possible.
- What happens when two canaries are detected in the same response (when wiring lands)? Single `security_events` row with `findings=["canary_leak"]` and the count; precedence still goes through 007 §FR-014 `max(risk_score)` rule.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST assemble system prompts from a fixed tier set `{low, mid, high, max}` using cumulative delta content (mid = low + mid-delta; high = low + mid-delta + high-delta; max = all four). The tier set is hardcoded in `src/prompts/tiers.py` (not runtime-configurable in Phase 1). Default tier when a participant has `prompt_tier` unset or unrecognized MUST be `mid`. Skipping intermediate tiers (e.g., low+high without mid) is NOT supported — `prompt_tier` selects the highest tier and lower tiers are always included.
- **FR-002**: System MUST append the participant's custom `system_prompt` after tier content. The custom prompt MUST be sanitized (FR-001 of 007: ChatML / role markers / override phrases / invisible Unicode stripped) before inclusion, because participant-supplied content is untrusted relative to operator-controlled tier text. Tier text itself is fixed English prose and does not need sanitization.
- **FR-003**: System MUST embed **three** canary tokens in each assembled system prompt at positions: (1) before all tier content, (2) between the first half and second half of the parts list (`max(1, len(parts) // 2)` join point), (3) after all tier and custom content. Each canary MUST be a 16-character RFC 4648 upper-case base32 string with no padding (10 random bytes via `secrets.token_bytes`, ≥80 bits entropy — sufficient that brute-force enumeration is infeasible while keeping the marker visually compact). Canaries MUST be unique per assembly. **Detection wiring (FR-003.detect)**: scanning AI output for embedded canaries via `PromptProtector.check_leakage` is currently DEFERRED — the canaries are emitted but not checked. Wiring requires per-session canary persistence (the values must survive across the LLM round-trip) and is tracked as a Phase 3 follow-up. The interface stub already exists in `src/security/prompt_protector.py`.
- **FR-004**: System MUST sanitize all runtime messages during context assembly (see 007 §FR-001 for the canonical pattern set). The same sanitization function applies to the participant-supplied custom `system_prompt` per FR-002.
- **FR-005**: System MUST spotlight (datamark) AI messages from OTHER participants during context assembly. Same-speaker (an AI reading its own prior output), human, and system messages MUST NOT be datamarked — see 007 §FR-003 for the authoritative same-speaker exemption rule, enforced here at `src/orchestrator/context.py:_secure_content`. Datamark format follows 007 §FR-002 (`^<6-hex>^<word>` per whitespace-split word, 6-hex = SHA-256 prefix of source participant id).
- **FR-006**: System MUST run output validation (per 007 §FR-004) on AI responses before persistence. The "high risk" threshold is the same `>= 0.7` defined in 007 §FR-005.
- **FR-007**: System MUST run exfiltration filtering (per 007 §FR-006/§FR-007/§FR-008 — image strip, URL flagging, credential redaction including OpenAI / Anthropic / Gemini / Groq / JWT / Fernet) on AI responses before persistence.
- **FR-008**: System MUST stage high-risk responses for facilitator review instead of persisting them. Staging is implemented as a draft row in the review-gate table (`_stage_for_review` in `src/orchestrator/loop.py`) plus the operator-notification surfaces defined in 007 §FR-016 (review-gate UI banner, `security_events` row, WS `routing_mode` event). On facilitator approve / edit / reject, content is persisted verbatim per 007 §FR-005 — it does NOT re-enter the security pipeline.
- **FR-009**: Layer evaluation order in this wiring matches 007 §FR-014: validate → exfiltration filter, with each layer emitting independent flags / findings. Pipeline-internal failures (regex bug, unicode error, etc.) fail closed per 007 §FR-013: the turn is skipped with `reason=security_pipeline_error` and the participant is NOT penalized via the circuit breaker. Per-layer detections are persisted to `security_events` per 007 §FR-015.
- **FR-010**: Bypass paths (debug routes, direct DB inserts, test fixtures) are NOT required to flow through this wiring. Production turn-loop paths MUST flow through `_validate_and_persist`. Equivalent to 007 §SC-007 for the wiring surface.
- **FR-011**: Tier text composition MUST be memoized. The output of cumulative-delta assembly for each `prompt_tier` (low / mid / high / max) is fixed at module load — recomputing per turn is wasted work. Memoization key: `prompt_tier`; cache size: 4 entries (one per tier value); invalidation: process restart only (tier text is hardcoded). The per-assembly cost is then string concatenation of (cached tier text) + (sanitized custom_prompt) + (3 canaries).
- **FR-012**: Per-participant `custom_prompt` sanitization (FR-002) MUST be memoized at the participant-update boundary, NOT recomputed per turn. The sanitized form is stored on the participant record (or in an LRU cache keyed by `(participant_id, custom_prompt_hash)`) and reused across all turns until `custom_prompt` changes. This eliminates the most-frequent regex pass observed in the wiring (custom prompt rarely changes; many turns reuse the same value).
- **FR-013**: Per-turn wiring cost decomposition: `tier_assembly_ms` + `sanitize_messages_ms` + `spotlight_messages_ms` + `pipeline_total_ms` (cross-ref 007 §FR-022) MUST be captured into `routing_log` (cross-ref 003 §FR-030 stage timings). Aggregate `wiring_total_ms` is the sum of these. Without per-stage decomposition, regressions in any one wiring step are invisible against the broader turn-loop noise floor.
- **FR-014**: Pattern-list ReDoS guard: every regex added to `src/security/sanitizer.py`, `exfiltration.py`, `jailbreak.py`, `output_validator.py`, `scrubber.py`, `prompt_protector.py` (cross-ref 007 §FR-017) MUST be verified ReDoS-safe via `re.fullmatch` timing on a 10KB pathological input (`"a" * 10000` with adversarial suffixes). Any regex whose match time exceeds 100ms on the pathological input MUST be rewritten or rejected. This is a CI-gate-shaped requirement; without it, an open-ended pattern list creates a latent ReDoS surface that user-supplied messages could trigger.

- **SC-001**: Tier assembly produces token counts within +/- 15% of the documented budgets (low ~250, mid ~520, high ~480, max ~480) measured by the rough estimator (`max(len(text) // 4, 1)`). The +/- 15% tolerance accommodates wording refinement without forcing budget rewrites.
- **SC-002**: Sanitization runs on every runtime message AND on every participant-supplied custom `system_prompt` before context assembly. Spotlighting runs on every AI message from a different speaker (per FR-005 exemption rules).
- **SC-003**: Output validation and exfiltration filtering run on every AI response on production dispatch paths before persistence (see FR-010 / 007 §SC-007 for bypass-path scope).
- **SC-004**: Pipeline-internal failures (per FR-009) result in zero silent drops — every error path either persists a clean response or stages for review or skips with `reason=security_pipeline_error` and emits a `security_events` row with `layer=pipeline_error`.
- **SC-005**: Per-turn wiring overhead P95 (FR-013): `tier_assembly_ms` ≤ 1ms (memoized per FR-011), `sanitize_messages_ms` ≤ 20ms (scales with `SACP_CONTEXT_MAX_TURNS=20` × per-message regex), `spotlight_messages_ms` ≤ 10ms (scales with cross-speaker AI message count and word count), aggregate non-pipeline `wiring_total_ms` ≤ 30ms. Pipeline cost is accounted separately per 007 §SC-008.
- **SC-006**: Memoization effectiveness: the `tier_assembly_ms` P95 with FR-011 memoization MUST be at least 10× faster than the cold-start P95 (first call after process restart) — this is the verifiable shape of "memoization is actually happening." A regression here indicates the cache key got broken.

## Assumptions

- Tier content is constant text in Phase 1+2. Dynamic / per-session tier content is a Phase 3+ enhancement. **Re-evaluation triggers** (when this assumption must be revisited): (a) a confirmed need for per-use-case tier specialization, (b) >=3 sessions where operators ask for tier overrides, (c) a use case that requires injection of session-specific safety language at construction time.
- Tier token budgets are approximate (~250, ~520, ~480, ~480 for the deltas). Exact wording will be refined within the +/- 15% SC-001 tolerance. Larger drift requires a budget rewrite.
- Canary tokens are high-entropy random strings (16-char RFC 4648 base32, 80 bits entropy from `secrets.token_bytes(10)`). Three canaries are placed at start / middle / end of the assembled parts to catch selective extraction (an attacker that reveals only the head, only the tail, or only an interior fragment still triggers detection).
- **Canary detection wiring is deferred** (see FR-003.detect). The canaries are currently emitted but not scanned in the pipeline because per-session canary persistence is not implemented. Phase 3 follow-up: add a canary-storage column to `participants` (or `sessions`), thread the stored values through `assemble_prompt` so the same canaries are reused across turns within a session, and call `PromptProtector(check_leakage)` from `_run_pipeline`. Until this lands, system-prompt extraction defense relies on FR-011 of 007 (25-word fragment scan), which IS wired via the broader pipeline indirectly through future LLM-judge work.
- Canary detection response (when wired) MUST follow the same path as other high-risk findings: hold for facilitator review (FR-008), emit a `security_events` row with `layer=prompt_protector`, surface via the operator-notification path (007 §FR-016). Auto-block is out of scope per 007 §FR-018.
- Custom `system_prompt` is participant-supplied and treated as untrusted relative to tier content; tier content is operator-controlled (hardcoded in source). The trust gradient is: tier text > sanitized custom prompt > sanitized runtime messages.
- System prompt is re-assembled on every turn (every call to `_add_system_prompt` in `src/orchestrator/context.py`). This means canaries currently rotate every turn — which is fine while detection is unwired (no detection means rotation is harmless), but Phase 3 wiring MUST stabilize canaries per session so they survive across turns.

## Threat model traceability

008's wiring inherits the threat-model mapping from the sister spec [007-ai-security-pipeline](../007-ai-security-pipeline/spec.md#threat-model-traceability). This spec's FRs are the *integration* of 007's defenses into context assembly and the turn loop:

| 008 FR | 007 cross-ref | OWASP LLM | Note |
|--------|---------------|-----------|------|
| FR-001 (tiered prompts) | — | LLM07 | Tier text frames collaboration boundaries; canaries (FR-003) defend against extraction. |
| FR-002 (custom prompt sanitization) | 007 §FR-001 | LLM01 | Closes the participant-supplied-content injection surface that pure 007 wiring missed. |
| FR-003 (canaries) | 007 §FR-010, §FR-011 | LLM07 | Wiring inherits 007's multi-canary mandate; detection wiring is deferred (Phase 3). |
| FR-004, FR-005 (sanitize / spotlight in context) | 007 §FR-001, §FR-002, §FR-003 | LLM01 | Integration site for sanitizer + spotlight modules. |
| FR-006, FR-007, FR-008 (validate / exfil / stage) | 007 §FR-004, §FR-005, §FR-006-§FR-008, §FR-016 | LLM01, LLM02, LLM05, LLM06 | Integration site for output_validator + exfiltration filter; staging path matches 007's operator-notification surface. |
| FR-009 (precedence + fail-closed) | 007 §FR-013, §FR-014, §FR-015 | LLM05 | Fail-closed and `security_events` persistence inherited verbatim from 007. |
| FR-010 (bypass scope) | 007 §SC-007 | LLM05 | Bypass-path stance matches 007. |

## Audit closeout (2026-04-29)

The security-requirements quality audit (`checklists/security.md`) raised 44 findings; resolution split:

**Code changes**: CHK003 / CHK032 (custom-prompt sanitized before assembly in `src/prompts/tiers.py`).

**Spec amendments (this commit)**: CHK001 / CHK002 (FR-001 tier set + stacking pinned), CHK004 / CHK013 / CHK018 (FR-003 canary placement specified), CHK005 / CHK006 / CHK007 / CHK023 / CHK027 / CHK036 (canary detection wiring codified as deferred with stored interface stub + Phase 3 trigger), CHK008 / CHK024 (FR-009 fail-closed cross-ref), CHK009 / CHK041 / CHK044 (FR-008 staging path tied to 007 §FR-016), CHK010 (FR-010 bypass scope), CHK011 (FR-001 tier-set is fixed not "configurable"), CHK012 / CHK021 / CHK039 (SC-001 +/- 15% tolerance), CHK014 / CHK040 (FR-003 base32 RFC + entropy rationale), CHK015 (FR-006 cross-ref to 007 threshold), CHK016 / CHK042 (FR-005 same-speaker + datamark format cross-ref), CHK017 (FR-009 precedence cross-ref), CHK020 (Assumptions trust gradient), CHK022 (SC-002 includes custom prompt), CHK025 (FR-008 verbatim persistence on approve/edit), CHK028 (Assumptions re-assembly cadence), CHK030 (Edge case: empty custom + unrecognized tier), CHK031 (Edge case: MVC floor hard contract), CHK035 (Threat-model traceability table), CHK038 (Assumptions tier-content re-eval triggers), CHK043 (FR-007 explicit list of 007's covered patterns).

**Closed as accepted residual / out-of-scope** (documented in Edge Cases or Assumptions): CHK019 (multi-canary count consistent across spec/clarification/code), CHK026 (`assemble_prompt` defaults guarantee no error path on malformed input), CHK029 / CHK033 (canary / datamark shape collisions are impossible), CHK034 (assembly perf trivial — string concat + 30 chars random), CHK037 (a11y inherited from Phase 3 deferral in 007 CHK036).

## Operational notes (Phase F amendment, 2026-05-02)

These items capture operator-facing decisions that don't change behaviour but
are required for production deployment readiness. Cross-referenced from
`AUDIT_PLAN.local.md` Batch 5 → 008 ops.

**Prompt-tier env-var contract.** The four-tier set (`low` / `mid` / `high` /
`max`) is hardcoded in `src/prompts/tiers.py` at module load. There is NO
runtime override env var in Phase 1 — `prompt_tier` is read from the
participant record only. The default for an unset / unrecognized
`prompt_tier` is `mid` (FR-001). Operators that need per-deployment tier
overrides MUST treat that as a Phase 3 enhancement and reference the tier-
content re-evaluation triggers in Assumptions; ad-hoc env-var injection
into `_TIERS` is unsupported and not stable across releases.

**Canary-storage path (deferred wiring).** FR-003.detect is currently
unwired because per-session canary persistence has not been implemented.
The Phase 3 storage path SHALL add either (a) a `canaries TEXT[]` column on
`sessions` (per-session, all participants share), or (b) a
`canaries TEXT[]` column on `participants` (per-participant, distinct
values across the session). Option (a) keeps detection cheap (one set of
3 values to scan against every AI response in the session) but means a
participant who extracts another's canaries can claim leakage was theirs.
Option (b) raises detection cost linearly in participant count. Phase 3
decision deferred; document chosen path in this section when wired.
Migration MUST be additive (forward-only per 001 §FR-017) and not require
backfill — sessions created before the column exists simply have no canary
detection until the next assembly.

**Tier-text constancy triggers.** Per Assumptions: tier text is constant
in Phase 1+2. Operator demand re-evaluating this assumption requires:
(a) ≥3 sessions where operators ask for tier overrides, OR (b) a confirmed
need for per-use-case tier specialization (e.g. medical, legal, code-
review variants), OR (c) a use case requiring injection of session-
specific safety language at construction time. When triggered, the
implementation surface is a tier-content registry keyed on use-case
identifier, NOT inline env-var substitution. Refusal-to-add-knobs default
applies until one of the three triggers fires.

**ReDoS guard CI process (FR-014).** Every PR that adds or modifies a
regex in `src/security/sanitizer.py`, `exfiltration.py`, `jailbreak.py`,
`output_validator.py`, `scrubber.py`, or `prompt_protector.py` MUST pass
the `tests/test_008_testability.py::test_fr014_redos_guard_under_budget`
suite locally before merge. The current CI budget catches catastrophic
backtracking (10x-100x blowup); tightening to the 100ms-on-prod-hardware
threshold from FR-014 is a Phase 3 ReDoS-CI item. Reviewer of any new
regex MUST eyeball for nested quantifiers (`(a+)+`, `(a|a)*`, etc.) and
require either a Hypothesis fuzz test or a documented pathological
input sample alongside the change. Blast radius of failure is global:
a single ReDoS-vulnerable pattern reachable from `sanitize()` lets any
participant DoS the orchestrator's per-turn dispatch path.

**Memoization invalidation procedure (FR-011 / FR-012).** When the
deferred memoization caches land:
- FR-011 tier-text cache: 4 entries (one per tier), invalidated only on
  process restart. To force recomputation, restart `mcp_server` and
  `web_ui`. There is no runtime invalidation hook because tier text is
  hardcoded source — a tier-text change is a code change is a deploy.
- FR-012 custom-prompt sanitize cache: keyed on
  `(participant_id, hash(custom_prompt))`. Invalidated automatically on
  every participant update (via `update_participant`). Operators do NOT
  need to manually clear; if a stale entry is suspected, restarting the
  orchestrator drops the cache wholesale. There is no exposed admin
  endpoint to flush the sanitize cache by design — the only way a stale
  entry persists past an update is if `update_participant` is bypassed,
  which is itself a contract violation.

**Custom-prompt size limits (operational).** The participant-supplied
`custom_prompt` field is bounded by 002 §FR-A2 input-size limits at the
auth/registration boundary. 008 imposes no additional cap. Cross-ref
002 spec for the canonical limit; if 002 raises or lowers the cap, this
spec inherits the new value automatically (the wiring is the same
sanitize-then-store path).

## Topology and Use Case Coverage (V12/V13 retro-addendum, 2026-04-15)

**Topologies** (per constitution §3): All seven (1–7). System prompts (tiered, canary-protected) and security pipeline integration apply to all topologies — orchestrator-driven or peer-driven. Canary tokens, sanitization, and spotlighting are topology-neutral defenses.

**Use cases** (per constitution §1): Foundational for scenarios handling sensitive intellectual property (research co-authorship, consulting, technical audits, zero-trust cross-org). Prompt extraction defense prevents accidental leakage of system instructions.
