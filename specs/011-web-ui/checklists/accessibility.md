# Accessibility Requirements Quality Checklist: Web UI

**Purpose**: Validate the quality, clarity, and completeness of accessibility requirements in the Web UI spec — testing the *requirements themselves* (unit tests for English), not the shipped implementation.
**Created**: 2026-04-29
**Audited**: 2026-04-29
**Feature**: [spec.md](../spec.md)

**Audit summary**: 5 items pass cleanly, 33 have findings. The spec defers accessibility almost entirely (Assumptions: "Accessibility audit is a follow-up pass") and the audit closeout (CHK041) accepts that as a Phase 3 trigger. As a result, virtually no a11y requirements exist today — most items below are documented gaps. The intent here is to make the gap surface concrete enough that Phase 3 can convert findings into FRs/SRs without re-discovering them.

## Compliance Targets

- [x] CHK001 Is a target conformance level specified (WCAG 2.1 AA, WCAG 2.2 AA, ATAG)?
  [GAP]. Spec is silent. Phase 3 should pin a target — WCAG 2.2 AA is the modern enterprise default.

- [x] CHK002 Is the audit methodology specified (manual + automated, Lighthouse, axe-core, NVDA / JAWS / VoiceOver matrix)?
  [GAP]. No tooling or testing protocol named.

- [x] CHK003 Are exemption rules documented for components that cannot meet the conformance level (e.g. third-party CDN-loaded markdown library)?
  [GAP]. With the no-build-toolchain constraint (FR-002), DOMPurify / marked / React-from-CDN may have a11y limits worth declaring.

## Keyboard Navigation & Focus Management

- [x] CHK004 Are keyboard-only navigation requirements specified for the three-column layout (focus order across sidebars + transcript)?
  [GAP]. FR-007 names the layout but says nothing about Tab order. With sidebars + transcript + drawers (FR-008), the Tab graph is non-trivial.

- [x] CHK005 Is the Ctrl+Enter send shortcut (US1 AC3) documented as discoverable to keyboard users (visible hint, kbd element, aria-keyshortcuts)?
  [PARTIAL]. The shortcut exists but the spec doesn't require it to be announced to assistive tech or shown in UI. A user who can't press Ctrl+Enter would have no way to send.

- [x] CHK006 Are alternative keyboard paths required for every mouse-driven interaction (admin panel collapse, drawer open, sparkline tooltip, badge hover for skip reasons)?
  [GAP]. US10 AC3 specifies "hovering the health badge shows the last 3 skip reasons" — hover-only is a keyboard a11y bug.

- [x] CHK007 Is focus management specified for modals (token-reveal modal in US11 AC2, edit-draft modal in US5)?
  [GAP]. No focus-trap requirement; no return-focus-on-dismiss; no Esc-to-close mandate.

- [x] CHK008 Is focus management specified for the inline rename input (US11 AC4, click session name → input)?
  [GAP]. Spec doesn't require keyboard-triggerable rename or focus on the input when activated.

- [x] CHK009 Are focus indicators required to be visible (no `:focus { outline: 0 }`)? Is the indicator contrast specified?
  [GAP]. No requirement. With dark theme default (Assumptions), low-contrast focus rings are a real risk.

- [x] CHK010 Is keyboard-driven access to the review-gate queue (Approve/Edit/Reject buttons in US5) specified?
  [GAP]. Buttons are named but no Tab/Enter/Space contract.

## Screen Reader Support / ARIA / Semantic HTML

- [x] CHK011 Are landmark regions required (header / main / nav / aside / complementary) for the three-column layout?
  [GAP]. FR-007 names the layout in CSS terms; landmark mapping is unspecified.

- [x] CHK012 Are ARIA labels / accessible names required for interactive elements (icon-only buttons, the three-path landing in US11)?
  [GAP]. No mandate. US11 AC1 mentions "Sign in / Create / Request to join" but doesn't require buttons to expose accessible names beyond visible text.

- [x] CHK013 Is the participant list (left sidebar) required to use a semantic list structure (`role="list"` / `<ul>`) so screen reader users get count + index announcements?
  [GAP]. FR-007 silent on semantics.

- [x] CHK014 Is the transcript required to use semantic message structure (each message as a region/article with author + timestamp accessible)?
  [GAP]. Critical: a screen reader on a 200-message scrollback (Assumptions) needs landmark-jumpable messages, not a flat blob.

- [x] CHK015 Are ARIA roles specified for non-standard widgets (sparkline graph US4, convergence threshold line, budget bar)?
  [GAP]. Sparklines need `role="img"` + `aria-label` with summary text or a data-table fallback. Spec is silent.

- [x] CHK016 Are status-only icons required to have text alternatives (the "⚠ N hidden" badge in FR-006, breaker-tripped badge in US10 AC1)?
  [GAP]. Icons-as-status without `aria-label` is a common a11y bug.

- [x] CHK017 Is the connection-indicator in the header (mentioned in Phase 2a Core list) required to expose its state to assistive tech?
  [GAP]. WebSocket status changes silently to screen readers without an aria-live or label update mandate.

## Live Region / Real-Time Update Announcement

- [x] CHK018 Are real-time WebSocket events (new message, participant joined, breaker tripped) required to trigger ARIA live-region announcements?
  [GAP]. FR-014 + US3 deliver pushed events; spec has no requirement for announcing them. A blind facilitator could miss every AI turn.

- [x] CHK019 Is the live-region politeness level specified (polite vs. assertive) for different event classes?
  [GAP]. New AI turn = polite; breaker trip = assertive; spec doesn't differentiate.

- [x] CHK020 Is the timeout countdown for review-gate drafts (US5 AC3) required to be announced periodically without spamming?
  [GAP]. Critical for blind facilitators reviewing drafts under a deadline. No spec requirement for accessible countdown.

- [x] CHK021 Is the convergence-update sparkline (FR-011) required to announce significant threshold crossings?
  [GAP]. Sparkline visually indicates convergence; non-visual users have no equivalent signal.

- [x] CHK022 Are token-reveal / session-creation success messages (US11 AC2) required to be announced before focus moves?
  [GAP]. Race between aria-live announcement and focus shift to "enter the session" button is unspecified.

## Visual Accessibility

- [x] CHK023 Is color-contrast minimum specified for text vs. background (WCAG 4.5:1 AA, 7:1 AAA)?
  [GAP]. Dark-theme default (Assumptions) needs explicit contrast targets for low-vision users.

- [x] CHK024 Are color-only state indicators (budget bar color "as it approaches 100%" US4 AC1, breaker-tripped vs. paused-manual US10) required to have a non-color signal too?
  [GAP]. Budget-bar color is the only signal. WCAG 1.4.1 violation by default.

- [x] CHK025 Is light-theme support required, or accepted residual?
  [ACCEPTED]. Assumptions: "Dark theme default. Light theme toggle is desirable but not required." Worth re-evaluating for users with light-sensitivity (migraines, photophobia).

- [x] CHK026 Is responsive zoom-to-200% support required (WCAG 1.4.4)?
  [GAP]. FR-008 describes 1024px breakpoint but says nothing about zoom-without-horizontal-scroll.

- [x] CHK027 Is text-spacing-override compatibility required (WCAG 1.4.12)? Users with dyslexia override line-height / letter-spacing.
  [GAP].

## Reduced Motion & Cognitive Accessibility

- [x] CHK028 Is `prefers-reduced-motion` honored for animations (sparkline updates, drawer open/close, transcript auto-scroll)?
  [GAP]. No requirement. Auto-scroll on new message is a vestibular-trigger risk.

- [x] CHK029 Is auto-scroll on the transcript required to pause when the user has scrolled up (so screen-reader / keyboard users aren't yanked back)?
  [GAP]. Non-trivial UX with a11y implications, unspecified.

- [x] CHK030 Are session timeouts (US5 review-gate countdown, token expiration) required to offer extension or warning per WCAG 2.2.1?
  [GAP]. Auto-rejected drafts (US5 AC3) on timeout with no warning is a WCAG fail.

## Form & Input Accessibility

- [x] CHK031 Are form inputs (token paste, message compose, session ID for join, display name for create/join) required to have associated `<label>` elements?
  [GAP]. Standard a11y baseline; not in spec.

- [x] CHK032 Are validation errors (invalid token, taken session ID, scheme-blocked link in markdown) required to be announced and associated with the offending field via aria-describedby?
  [GAP].

- [x] CHK033 Is the markdown-input compose textarea (US1 AC3) required to expose its character limit (`MAX_MESSAGE_CONTENT_CHARS = 2_000` per SR-001a) accessibly?
  [GAP]. Sighted users can see "1234 / 2000"; screen-reader users have no equivalent unless an aria-describedby is mandated.

## Error & Status Communication

- [x] CHK034 Are error messages required to be perceivable by all users (not toast-only with auto-dismiss)?
  [GAP]. Toast notifications are a common a11y trap (announce-then-vanish before the user reaches them).

- [x] CHK035 Is the WebSocket-disconnected state (FR-014 reconnect attempts) required to be announced as it changes?
  [GAP]. Silent reconnects are a usability + a11y problem — sighted users see the indicator update; screen-reader users get nothing.

- [x] CHK036 Are graceful failures specified for assistive-tech-incompatible features (e.g. a sparkline that AT users cannot perceive — is a textual alternative required, like "convergence: 0.78, last-5 trend: rising")?
  [GAP].

## Internationalization / RTL

- [x] CHK037 Is the document `lang` attribute required and dynamic if multi-language content arrives via WebSocket?
  [GAP]. AI responses can mix languages; no mandate for `lang` annotation.

- [x] CHK038 Is RTL (right-to-left script) layout support required, or out of scope (deferred to Phase 3 with i18n)?
  [ACCEPTED]. Out of Scope explicitly lists "Internationalization." Worth pinning whether RTL render of message content is in or out — RTL content can leak into a session even without app i18n.

## Notes

- 38 items audited. Only CHK025 and CHK038 land as ACCEPTED (documented Phase 3 deferrals); the rest are GAPs. The reality: virtually no a11y requirements exist in the spec today.
- Highest-leverage findings to convert into spec amendments before Phase 3:
  - CHK001 (pin WCAG 2.2 AA as the conformance target — single sentence, sets the bar for everything else).
  - CHK006 / CHK020 (hover-only and timeout-only interactions are existing keyboard / cognitive a11y bugs in shipped UI).
  - CHK018 (live-region announcement of WebSocket events — the highest-impact change for blind facilitators using the dashboard).
  - CHK024 (color-only state signals — already shipped, easy retrofit).
- Lower-priority groundwork:
  - CHK011 / CHK013 / CHK014 (semantic HTML + landmarks — refactor of `frontend/app.jsx` rendering layer).
  - CHK023 / CHK026 / CHK027 (contrast + zoom + text-spacing — CSS audit).
- Phase 3 trigger documented in Assumptions ("Accessibility audit is a follow-up pass") + audit closeout CHK041 — this checklist is the concrete punch-list that closes that trigger.
- Sister checklist `requirements.md` covered general spec quality; `security.md` covered security requirements; this one drills into accessibility-specific requirement quality. Next sister: `ux.md` (Tier 2 queue).
