#!/usr/bin/env node
/* SACP frontend test — participant re-join identity indicator.
 *
 * Pure-Node test for the logic in frontend/rejoin_indicator.js. The
 * detection + lifecycle helpers are pure JS (no React, no browser);
 * they import and run directly under Node.
 *
 * Run:
 *   node tests/frontend/test_rejoin_indicator.js
 *
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "rejoin_indicator.js"));
const {
  REJOIN_PILL_WINDOW_TURNS,
  shortIdBadge,
  findPriorRemovedSameName,
  shouldShowRejoinedPill,
  buildIdentityTooltip,
  applyLifecycleOnUpdate,
  applyLifecycleOnRemove,
  seedLifecycleFromSnapshot,
} = MOD;

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log("PASS  " + name);
    passed += 1;
  } catch (e) {
    console.error("FAIL  " + name);
    console.error("      " + (e && e.stack ? e.stack : e));
    failed += 1;
  }
}

// ---------------------------------------------------------------------------
// shortIdBadge — always-on last-4-char badge
// ---------------------------------------------------------------------------

test("badge always renders last 4 chars of participant_id", () => {
  assert.strictEqual(shortIdBadge("abcdef0123456789fb90"), "fb90");
  assert.strictEqual(shortIdBadge("0123456789ABCDEFFB90"), "fb90", "should lowercase");
});

test("badge handles short ids gracefully", () => {
  assert.strictEqual(shortIdBadge("abc"), "abc");
  assert.strictEqual(shortIdBadge(""), "");
  assert.strictEqual(shortIdBadge(null), "");
  assert.strictEqual(shortIdBadge(undefined), "");
});

test("badge accepts a custom length", () => {
  assert.strictEqual(shortIdBadge("abcdef0123456789", 6), "456789");
  assert.strictEqual(shortIdBadge("abcdef0123456789", 0), "6789",
    "zero or negative falls back to default 4");
});

// ---------------------------------------------------------------------------
// findPriorRemovedSameName — case/whitespace handling
// ---------------------------------------------------------------------------

test("findPriorRemovedSameName returns null when no prior departed match", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Sage", status: "removed" },
  ];
  assert.strictEqual(findPriorRemovedSameName(active, list), null);
});

test("findPriorRemovedSameName matches case-insensitively", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "KAREN", status: "removed" },
  ];
  const result = findPriorRemovedSameName(active, list);
  assert.ok(result);
  assert.strictEqual(result.id, "b2");
});

test("findPriorRemovedSameName trims whitespace", () => {
  const active = { id: "a1", display_name: "  Karen  ", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Karen", status: "offline" },
  ];
  const result = findPriorRemovedSameName(active, list);
  assert.ok(result);
});

test("findPriorRemovedSameName recognises offline / removed / reset as departed", () => {
  for (const status of ["offline", "removed", "reset"]) {
    const active = { id: "a1", display_name: "Karen", status: "active" };
    const list = [
      active,
      { id: "b2", display_name: "Karen", status },
    ];
    const result = findPriorRemovedSameName(active, list);
    assert.ok(result, "should match when prior status is " + status);
  }
});

test("findPriorRemovedSameName does not match against non-departed status", () => {
  for (const status of ["active", "pending", "approved"]) {
    const active = { id: "a1", display_name: "Karen", status: "active" };
    const list = [
      active,
      { id: "b2", display_name: "Karen", status },
    ];
    const result = findPriorRemovedSameName(active, list);
    assert.strictEqual(result, null,
      "should NOT match when prior status is " + status);
  }
});

test("findPriorRemovedSameName ignores self (same id)", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [active];
  assert.strictEqual(findPriorRemovedSameName(active, list), null);
});

// ---------------------------------------------------------------------------
// shouldShowRejoinedPill — the pill gating
// ---------------------------------------------------------------------------

test("Re-joined pill renders when prior departed same-name and within window", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    a1: { first_observed_turn: 30, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  assert.strictEqual(shouldShowRejoinedPill(active, list, 34, lifecycle), true);
});

test("Re-joined pill disappears after N turns past join", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    a1: { first_observed_turn: 30, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  // Within window (default 10 turns)
  assert.strictEqual(shouldShowRejoinedPill(active, list, 34, lifecycle), true);
  // At window boundary (currentTurn - first_observed_turn === windowTurns)
  // is the first turn the pill stops showing (strict <).
  assert.strictEqual(shouldShowRejoinedPill(active, list, 40, lifecycle), false);
  // Well past window
  assert.strictEqual(shouldShowRejoinedPill(active, list, 100, lifecycle), false);
});

test("Re-joined pill respects custom window override", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    a1: { first_observed_turn: 30, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  // Custom window=2: turn 31 inside, turn 32 outside.
  assert.strictEqual(shouldShowRejoinedPill(active, list, 31, lifecycle, 2), true);
  assert.strictEqual(shouldShowRejoinedPill(active, list, 32, lifecycle, 2), false);
});

test("Re-joined pill does NOT render for participants from snapshot (first_observed_turn null)", () => {
  // Pre-existing participants seeded by state_snapshot have null
  // first_observed_turn. They MUST NOT trigger the pill — we don't
  // know when they actually joined.
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    a1: { first_observed_turn: null, first_observed_iso: null },
  };
  assert.strictEqual(shouldShowRejoinedPill(active, list, 34, lifecycle), false);
});

test("Re-joined pill does NOT render without a prior departed match", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [active];
  const lifecycle = {
    a1: { first_observed_turn: 30, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  assert.strictEqual(shouldShowRejoinedPill(active, list, 31, lifecycle), false);
});

test("Re-joined pill does NOT render for non-active participants", () => {
  const departed = { id: "a1", display_name: "Karen", status: "removed" };
  const list = [
    departed,
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    a1: { first_observed_turn: 30, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  assert.strictEqual(shouldShowRejoinedPill(departed, list, 31, lifecycle), false);
});

// ---------------------------------------------------------------------------
// Tooltip composition
// ---------------------------------------------------------------------------

test("Tooltip includes participant_id, join time, and prior-removal time when applicable", () => {
  const active = {
    id: "01ARZ3NDEKTSV4RRFFQ69G5FAV",
    display_name: "Karen",
    status: "active",
  };
  const list = [
    active,
    { id: "01ARZ3NDEKTSV4RRFFQ69G5OLD", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    [active.id]: {
      first_observed_turn: 30,
      first_observed_iso: "2026-05-07T12:00:00Z",
    },
    "01ARZ3NDEKTSV4RRFFQ69G5OLD": {
      removed_at_turn: 28,
      removed_at_iso: "2026-05-07T11:55:00Z",
    },
  };
  const tooltip = buildIdentityTooltip(active, list, lifecycle, "en-US");
  assert.ok(tooltip.includes("ID: " + active.id), "missing ID line");
  assert.ok(tooltip.includes("Joined:"), "missing join line");
  assert.ok(tooltip.includes("Prior same-name removed:"),
    "missing prior-removal line");
});

test("Tooltip omits join line when first_observed_iso is missing", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const lifecycle = { a1: { first_observed_iso: null } };
  const tooltip = buildIdentityTooltip(active, [active], lifecycle, "en-US");
  assert.ok(tooltip.includes("ID: a1"));
  assert.ok(!tooltip.includes("Joined:"));
});

test("Tooltip notes time-unavailable when prior-removal iso missing", () => {
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const list = [
    active,
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = {
    a1: { first_observed_iso: "2026-05-07T12:00:00Z" },
    b2: {}, // no removed_at_iso seeded
  };
  const tooltip = buildIdentityTooltip(active, list, lifecycle);
  assert.ok(tooltip.includes("Prior same-name removed: (time unavailable)"));
});

// ---------------------------------------------------------------------------
// Lifecycle reducer helpers
// ---------------------------------------------------------------------------

test("applyLifecycleOnUpdate captures first_observed for newly seen participants", () => {
  const prev = {};
  const updated = { id: "a1", display_name: "Karen", status: "active" };
  const next = applyLifecycleOnUpdate(prev, [], updated, 5, "2026-05-07T12:00:00Z");
  assert.strictEqual(next.a1.first_observed_turn, 5);
  assert.strictEqual(next.a1.first_observed_iso, "2026-05-07T12:00:00Z");
});

test("applyLifecycleOnUpdate captures removed_at when status flips to departed", () => {
  const updated = { id: "a1", display_name: "Karen", status: "removed" };
  const prevParticipants = [{ id: "a1", display_name: "Karen", status: "active" }];
  const prev = { a1: { first_observed_turn: 5, first_observed_iso: "2026-05-07T12:00:00Z" } };
  const next = applyLifecycleOnUpdate(prev, prevParticipants, updated, 12, "2026-05-07T13:00:00Z");
  assert.strictEqual(next.a1.first_observed_turn, 5, "preserves join data");
  assert.strictEqual(next.a1.removed_at_turn, 12);
  assert.strictEqual(next.a1.removed_at_iso, "2026-05-07T13:00:00Z");
});

test("applyLifecycleOnUpdate resets join window on re-add (departed → active)", () => {
  const updated = { id: "a1", display_name: "Karen", status: "active" };
  const prevParticipants = [{ id: "a1", display_name: "Karen", status: "removed" }];
  const prev = {
    a1: {
      first_observed_turn: 5,
      first_observed_iso: "2026-05-07T12:00:00Z",
      removed_at_turn: 10,
      removed_at_iso: "2026-05-07T12:30:00Z",
    },
  };
  const next = applyLifecycleOnUpdate(prev, prevParticipants, updated, 15, "2026-05-07T13:00:00Z");
  assert.strictEqual(next.a1.first_observed_turn, 15, "should reset to new join turn");
  assert.strictEqual(next.a1.first_observed_iso, "2026-05-07T13:00:00Z");
  assert.strictEqual(next.a1.removed_at_turn, null);
  assert.strictEqual(next.a1.removed_at_iso, null);
});

test("applyLifecycleOnRemove sets removed_at_* fields", () => {
  const prev = {
    a1: { first_observed_turn: 5, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  const next = applyLifecycleOnRemove(prev, "a1", 12, "2026-05-07T13:00:00Z");
  assert.strictEqual(next.a1.removed_at_turn, 12);
  assert.strictEqual(next.a1.removed_at_iso, "2026-05-07T13:00:00Z");
  assert.strictEqual(next.a1.first_observed_turn, 5, "preserves join data");
});

test("seedLifecycleFromSnapshot sets first_observed_turn=null for pre-existing", () => {
  const list = [
    { id: "a1", display_name: "Karen", status: "active" },
    { id: "b2", display_name: "Karen", status: "removed" },
  ];
  const lifecycle = seedLifecycleFromSnapshot(list, "2026-05-07T12:00:00Z");
  assert.strictEqual(lifecycle.a1.first_observed_turn, null,
    "pre-existing active should have null first_observed_turn");
  assert.strictEqual(lifecycle.b2.first_observed_turn, null);
  // Departed entries should have a removed_at_iso seed (best-effort).
  assert.strictEqual(lifecycle.b2.removed_at_iso, "2026-05-07T12:00:00Z");
  assert.strictEqual(lifecycle.b2.removed_iso_is_approximate, true);
});

// ---------------------------------------------------------------------------
// Cross-session scope (the brief calls this out explicitly)
// ---------------------------------------------------------------------------

test("Coincidental same-name across separate sessions does NOT trigger re-joined", () => {
  // The detection function only sees the participants list passed in,
  // which is per-session. Verify by constructing a list that contains
  // ONLY the active participant (no prior in the same list) — the
  // pill must not fire even when a different session in the universe
  // had a same-name removed entry.
  const active = { id: "a1", display_name: "Karen", status: "active" };
  const sessionAList = [active]; // session A's participant list — no prior
  // (Imagine session B somewhere with a removed Karen — irrelevant.)
  const lifecycle = {
    a1: { first_observed_turn: 30, first_observed_iso: "2026-05-07T12:00:00Z" },
  };
  assert.strictEqual(shouldShowRejoinedPill(active, sessionAList, 34, lifecycle), false,
    "single-session list with no prior should not trigger pill");
});

// ---------------------------------------------------------------------------
// Integration: full lifecycle flow
// ---------------------------------------------------------------------------

test("integration: add → remove → re-add produces expected lifecycle + pill state", () => {
  // Step 1: empty start
  let lifecycle = {};
  let participants = [];

  // Step 2: Karen added at turn 5 (first observation)
  const karenV1 = { id: "k1", display_name: "Karen", status: "active" };
  lifecycle = applyLifecycleOnUpdate(lifecycle, participants, karenV1, 5, "2026-05-07T12:00:00Z");
  participants = [karenV1];
  assert.strictEqual(lifecycle.k1.first_observed_turn, 5);

  // Step 3: Karen removed at turn 10
  const karenV1Removed = { ...karenV1, status: "removed" };
  lifecycle = applyLifecycleOnUpdate(lifecycle, participants, karenV1Removed, 10, "2026-05-07T12:30:00Z");
  participants = [karenV1Removed];
  assert.strictEqual(lifecycle.k1.removed_at_turn, 10);

  // Step 4: a NEW Karen (different id) added at turn 15
  const karenV2 = { id: "k2", display_name: "Karen", status: "active" };
  lifecycle = applyLifecycleOnUpdate(lifecycle, participants, karenV2, 15, "2026-05-07T13:00:00Z");
  participants = [karenV1Removed, karenV2];
  assert.strictEqual(lifecycle.k2.first_observed_turn, 15);

  // Step 5: pill should show on karenV2 at turn 15..24 (window=10)
  for (const t of [15, 16, 20, 24]) {
    assert.strictEqual(shouldShowRejoinedPill(karenV2, participants, t, lifecycle), true,
      "pill should show at turn " + t);
  }
  // Step 6: pill should disappear at turn 25+
  for (const t of [25, 30, 100]) {
    assert.strictEqual(shouldShowRejoinedPill(karenV2, participants, t, lifecycle), false,
      "pill should NOT show at turn " + t);
  }
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
