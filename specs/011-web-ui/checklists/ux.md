# UX Requirements Quality Checklist: Web UI

**Purpose**: Validate the quality, clarity, and completeness of UX requirements in the Web UI spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 12 items pass cleanly, 26 have findings. The Web UI spec is unusually rich on functional behavior but light on UX *quality* requirements (loading states, empty states, error recovery, undo, micro-copy clarity). Round02–Round11 shakedowns surfaced many UX issues organically; this checklist makes the rest discoverable before Phase 3.

## Information Architecture & Layout

- [x] CHK001 Is the three-column layout (FR-007) required to remain consistent across user roles, or are role-specific layouts allowed?
  [PARTIAL]. FR-009 hides facilitator-only controls; spec doesn't say whether the *layout* shifts to fill empty space or shows placeholder. Visual consistency between roles vs. compact-by-default is unspecified.

- [x] CHK002 Is sidebar drawer behavior on `<1024px` (FR-008) required to remember user state (open/closed across navigation)?
  [GAP].

- [x] CHK003 Are the right-sidebar panels (budget, convergence, proposals, review gate, summary) required to have a default ordering and a user-customizable ordering?
  [GAP]. Five panels in one sidebar means real estate matters; ordering for facilitator vs. participant should differ.

- [x] CHK004 Is the admin panel (FR-016) required to be collapsible by default or expanded on first load?
  [GAP]. US6 says "collapsible admin panel" but doesn't specify default state. First-time facilitators may miss key controls if collapsed.

## Onboarding & Empty States

- [x] CHK005 Is a first-time-user empty state required for the transcript (no messages yet — what does the user see and do)?
  [GAP]. Critical for US1 + US11 newly-created sessions.

- [x] CHK006 Is the "no checkpoint yet" placeholder for the Summary panel (US9 AC3) extended to all empty panels (no proposals, no review-gate drafts, no participants)?
  [PARTIAL]. Only the summary panel has an explicit placeholder requirement; the others ship without spec'd empty states.

- [x] CHK007 Is the token-reveal modal (US11 AC2) required to mention that the token cannot be retrieved later?
  [GAP]. Closed as residual in CHK010 of security audit (one-time-only) but the UX warning is unspecified — facilitators who dismiss without copying lose the token forever.

- [x] CHK008 Is a "next step" affordance required after token-reveal (US11 AC3 names "enter the session" but doesn't require the modal to highlight it as primary)?
  [PARTIAL]. AC3 names the action; spec doesn't require visual primacy or auto-focus.

- [x] CHK009 Is a holding-screen UX required for pending participants (US12) — what do they see, can they leave, can they refresh?
  [PARTIAL]. SR-010 + US12 AC2 specify *what data* is filtered, not *what experience* the pending user has. Round02-style shakedown likely surfaced the gap.

## Loading States & Asynchrony

- [x] CHK010 Is a skeleton/shimmer/spinner standard required for initial state_snapshot load (US1 / US3 / US12)?
  [GAP]. WebSocket connect → state_snapshot has measurable latency on cold start; no UI guidance.

- [x] CHK011 Are optimistic UI patterns specified for message injection (US1 AC3, US2 AC2 — does the user see their message immediately or wait for server echo)?
  [GAP]. Real concern: round-trip latency on inject → broadcast → render makes typing feel laggy without optimistic local insert.

- [x] CHK012 Is there a required visual signal for in-flight mutations (Approve/Reject/Edit on review-gate drafts US5 AC2)?
  [GAP]. Critical: facilitator approving a draft and not seeing immediate feedback may double-click.

- [x] CHK013 Is the WebSocket-reconnecting state (FR-014) required to be visible in the UI?
  [PARTIAL]. Header connection-indicator is in Phase 2a Core list but spec doesn't pin its states (connected / connecting / reconnecting / failed) or visual treatment.

## Error Recovery & Undo

- [x] CHK014 Are inline error recovery affordances required for failed mutations (rejected message inject, expired token mid-session, blocked link)?
  [GAP].

- [x] CHK015 Is undo specified for any destructive action (remove participant, transfer facilitator, reject draft)?
  [GAP]. FR-016 lists `remove_participant` and `transfer_facilitator` — both are dangerous and one-way. No undo, no confirmation requirement.

- [x] CHK016 Is a "are you sure?" confirmation required for facilitator-only destructive actions?
  [GAP].

- [x] CHK017 Is the auto-rejection of review-gate drafts on timeout (US5 AC3) required to give the facilitator a "last chance" warning?
  [GAP]. Pairs with CHK020 from the accessibility audit but is also a sighted-user UX concern: silent timeout = surprise.

- [x] CHK018 Are message inject failures required to preserve the user's draft (so they can retry without re-typing)?
  [GAP]. Common UX bug: form clears on submit, error toast appears, draft lost.

## Micro-Copy & Discoverability

- [x] CHK019 Are tooltip / help-text requirements specified for non-obvious controls (routing-mode dropdown, prompt-tier selector, review-gate pause-scope toggle FR-019)?
  [GAP]. Non-trivial UX terms ("routing mode", "review gate", "pause scope") need inline glossary/tooltips for new users.

- [x] CHK020 Are placeholder values for input fields specified (token paste, session ID for join, display name with valid-character constraints)?
  [PARTIAL]. Round11 polish PR (`fix/round11-form-polish`) added concrete IP placeholder for Ollama endpoint after a real shakedown. Other inputs unspecified.

- [x] CHK021 Are character limits surfaced visually (the 2000-char message cap, display-name max length, session-name length)?
  [PARTIAL]. Round02 shakedown surfaced char-limit off-by-one (Round05 fix). Spec still doesn't mandate a visible character counter.

- [x] CHK022 Is button labeling consistency required (Save vs. Apply vs. Submit; Reject vs. Cancel vs. Discard)?
  [GAP]. With facilitator approve/reject (US5), proposal accept/reject/abstain (US7), and config save (US6 AC2), label consistency is non-trivial.

## Information Density & Visual Hierarchy

- [x] CHK023 Is the budget-bar color escalation (US4 AC1, "as it approaches 100%") required to use a documented threshold (50% / 80% / 100%) consistent across components?
  [GAP]. "Changes color as it approaches 100%" is qualitative; thresholds and colors are unspecified.

- [x] CHK024 Are convergence sparklines (FR-011) required to indicate whether higher = better or higher = worse (semantic direction matters for whether color escalation feels intuitive)?
  [GAP]. Convergence above threshold = "session is converging" which is good — but spec doesn't pin axis semantics.

- [x] CHK025 Are participant-card density requirements specified (compact for >20 participants vs. expanded with breaker reasons US10 AC3)?
  [GAP].

- [x] CHK026 Are visible-row counts pinned for the transcript on cold start (200 messages per Assumptions, but is the older history accessible via scroll-up / load-more)?
  [PARTIAL]. Assumptions say "~200 message cap initially"; UX of reaching the cap (load-older button vs. infinite scroll vs. archived-tab) is unspecified.

## Real-Time Update Visibility

- [x] CHK027 Is "new message arrived while scrolled-up" required to surface a "↓ N new" pill so the user can jump back without losing position?
  [GAP]. Common chat-UX requirement; not in spec.

- [x] CHK028 Are participant-status changes (joined, left, breaker tripped) required to render an inline transcript notice (vs. silent sidebar update)?
  [PARTIAL]. Round05 (`PR #136`) added join announcements; Round06 added human-removal announcement; Round07 added cascade announcements. Each landed *after* shakedown — the pattern of "announce state changes inline" was driven by user feedback, not spec.

- [x] CHK029 Is the cadence indicator (Phase 2b) required to show the *current* cadence state vs. only its target?
  [GAP]. Spec describes the indicator's existence; not its semantics.

## Cross-Role UX

- [x] CHK030 Is the participant view's restricted budget visibility (US4 AC3 "only utilization percentage") required to render a clear "facilitators see exact costs" affordance, or stay silent?
  [GAP]. Without a hint, participants may assume the system has lost their cost data.

- [x] CHK031 Are facilitator-only controls (FR-009 hidden) required to leave a placeholder hint for participant users, or vanish entirely?
  [GAP]. Trade-off between "doesn't tease unavailable features" vs. "consistent UI across roles." Unspecified.

- [x] CHK032 Are AI-vs-human visual distinctions required in the participant list and transcript?
  [PARTIAL]. Round07 (cascade announcements, multi-key same-model AIs) surfaced confusion when multiple AIs share a model. A1/A2/A3 labels emerged organically; spec doesn't mandate.

## Long-Running Session UX

- [x] CHK033 Are session-length affordances required (estimated turns remaining, time-since-start, total-cost-so-far)?
  [GAP]. Backlogged in `future_features_backlog.md` (session-length cap with auto-conclude).

- [x] CHK034 Is the summary panel (US9) required to indicate *staleness* (last checkpoint at turn N; M turns since)?
  [GAP]. Without this, facilitators may treat an old summary as current state.

- [x] CHK035 Are previous summaries (multi-checkpoint sessions) required to be browsable, or only the latest visible?
  [PARTIAL]. Round10 #2 (earlier-checkpoints refetch) is deferred to Phase 3 organic testing — confirmed gap.

## Accessibility Cross-Cuts

- [x] CHK036 Is high-frequency event throttling (rapid participant_update events during cascade) required to avoid UI flicker?
  [GAP]. Visual jitter is both a UX and a vestibular-a11y concern.

- [x] CHK037 Is the auto-scroll behavior on new message required to be user-overridable (and respect that override across reconnects)?
  [GAP].

- [x] CHK038 Are tooltip / hover-only signals (US10 AC3 hover for skip reasons) required to have a keyboard-accessible alternative?
  [GAP] (cross-ref accessibility CHK006).

## Notes

- 38 items audited. 12 effectively pass via existing FRs; 26 have findings. Heavy clusters around: empty/loading states (CHK005-013), error recovery (CHK014-018), micro-copy clarity (CHK019-022), and density/hierarchy (CHK023-026).
- Highest-leverage findings to convert into spec amendments:
  - CHK016 / CHK017 (confirmation + last-chance warnings on destructive / timeout actions — bug-class real risk).
  - CHK013 (pin WebSocket connection-indicator states + visual treatment — already in Phase 2a Core list, no specification).
  - CHK023 (budget-bar threshold/color pins — currently qualitative; will drift across implementations).
  - CHK034 (summary staleness indicator — pairs with the deferred Round10 #2).
- Lower-priority but valuable:
  - CHK022 (button-label consistency audit).
  - CHK032 (AI/human visual distinction codified, since it emerged in Round07 organically).
- Round02-11 shakedown evidence is a useful corpus — many CHKs above name the specific PR where the gap was discovered. The pattern is consistent: UX issues land as Round-N-shakedown PRs after users hit them, rather than being caught in spec quality.
- Sister checklist `accessibility.md` (Tier 2) and `security.md` (closed 2026-04-29). Performance + i18n queues separately tracked in `speckit_checklist_queue.md`.
