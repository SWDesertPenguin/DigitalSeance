#!/usr/bin/env node
/* SACP frontend test - audit-log filter logic (spec 029 FR-012 / US3 / T042).
 *
 * Pure-Node test for frontend/audit_filters.js. Run:
 *   node tests/frontend/test_filter_logic.js
 *
 * Exit code: 0 = all pass; 1 = any failure.
 *
 * Covers single-axis matches, multi-axis intersections, the
 * orchestrator-actor sentinel, time-range edge cases, and the
 * "no filters means full input" invariant. The component layer
 * relies on isEmpty() to short-circuit the (N hidden) badge so
 * the test asserts that contract too.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "audit_filters.js"));
const {
  ORCHESTRATOR_ACTOR_KEY,
  TIME_PRESETS,
  EMPTY_FILTERS,
  matchesFilters,
  applyFilters,
  isEmpty,
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
// Fixtures - timestamps anchored to a fixed "now" so the time-range
// tests are deterministic regardless of when the suite runs.
// ---------------------------------------------------------------------------

const NOW_MS = Date.UTC(2026, 4, 8, 12, 0, 0); // 2026-05-08T12:00:00Z
const ALICE = "00000000-0000-0000-0000-00000000a11c";
const BOB   = "00000000-0000-0000-0000-00000000b0bb";

function isoFromNow(deltaSec) {
  return new Date(NOW_MS + deltaSec * 1000).toISOString();
}

function row(overrides) {
  return Object.assign({
    id: "row-" + Math.random().toString(16).slice(2, 8),
    timestamp: isoFromNow(0),
    actor_id: ALICE,
    actor_display_name: "Alice",
    action: "add_participant",
    action_label: "Facilitator added participant",
    target_id: null,
    target_display_name: null,
    previous_value: null,
    new_value: null,
    summary: null,
  }, overrides || {});
}

const rows = [
  row({ id: "r1", actor_id: ALICE, action: "add_participant",       timestamp: isoFromNow(-30 * 60) }),       // 30 min ago
  row({ id: "r2", actor_id: ALICE, action: "review_gate_approve",   timestamp: isoFromNow(-3 * 60 * 60) }),    // 3 h ago
  row({ id: "r3", actor_id: BOB,   action: "add_participant",       timestamp: isoFromNow(-2 * 24 * 60 * 60) }), // 2 d ago
  row({ id: "r4", actor_id: null,  action: "auto_pause_on_cap",     timestamp: isoFromNow(-15 * 60) }),         // 15 min ago, orchestrator
  row({ id: "r5", actor_id: ALICE, action: "rotate_token",          timestamp: isoFromNow(-10 * 24 * 60 * 60) }), // 10 d ago
];

// ---------------------------------------------------------------------------
// Module shape
// ---------------------------------------------------------------------------

test("module exports the documented surface", () => {
  assert.strictEqual(typeof matchesFilters, "function");
  assert.strictEqual(typeof applyFilters, "function");
  assert.strictEqual(typeof isEmpty, "function");
  assert.strictEqual(typeof ORCHESTRATOR_ACTOR_KEY, "string");
  assert.ok(Array.isArray(TIME_PRESETS));
  assert.ok(TIME_PRESETS.length >= 2);
  assert.strictEqual(typeof EMPTY_FILTERS, "object");
});

test("EMPTY_FILTERS represents the unfiltered state", () => {
  assert.strictEqual(EMPTY_FILTERS.actor, null);
  assert.strictEqual(EMPTY_FILTERS.action, null);
  assert.strictEqual(EMPTY_FILTERS.timePreset, "all");
  assert.ok(isEmpty(EMPTY_FILTERS));
});

test("TIME_PRESETS includes 'all' as the no-op default", () => {
  const allPreset = TIME_PRESETS.find((p) => p.key === "all");
  assert.ok(allPreset);
  assert.strictEqual(allPreset.seconds, null);
});

// ---------------------------------------------------------------------------
// isEmpty
// ---------------------------------------------------------------------------

test("isEmpty true for null/undefined/empty filter", () => {
  assert.ok(isEmpty(null));
  assert.ok(isEmpty(undefined));
  assert.ok(isEmpty({}));
  assert.ok(isEmpty({ actor: null, action: null, timePreset: "all" }));
});

test("isEmpty false when any axis is active", () => {
  assert.ok(!isEmpty({ actor: ALICE, action: null, timePreset: "all" }));
  assert.ok(!isEmpty({ actor: null, action: "add_participant", timePreset: "all" }));
  assert.ok(!isEmpty({ actor: null, action: null, timePreset: "1h" }));
});

// ---------------------------------------------------------------------------
// applyFilters - empty input cases
// ---------------------------------------------------------------------------

test("applyFilters returns full input when filters empty", () => {
  const out = applyFilters(rows, EMPTY_FILTERS, NOW_MS);
  assert.strictEqual(out.length, rows.length);
  assert.notStrictEqual(out, rows, "must return a new array, not the original");
});

test("applyFilters returns [] for non-array input", () => {
  assert.deepStrictEqual(applyFilters(null, EMPTY_FILTERS, NOW_MS), []);
  assert.deepStrictEqual(applyFilters(undefined, EMPTY_FILTERS, NOW_MS), []);
  assert.deepStrictEqual(applyFilters("nope", EMPTY_FILTERS, NOW_MS), []);
});

// ---------------------------------------------------------------------------
// Single-axis: actor
// ---------------------------------------------------------------------------

test("actor filter narrows to that actor's rows", () => {
  const out = applyFilters(rows, { actor: ALICE, action: null, timePreset: "all" }, NOW_MS);
  assert.deepStrictEqual(out.map((r) => r.id).sort(), ["r1", "r2", "r5"]);
});

test("actor filter ORCHESTRATOR_ACTOR_KEY matches null actor_id", () => {
  const out = applyFilters(
    rows,
    { actor: ORCHESTRATOR_ACTOR_KEY, action: null, timePreset: "all" },
    NOW_MS,
  );
  assert.deepStrictEqual(out.map((r) => r.id), ["r4"]);
});

test("actor filter on unknown id returns []", () => {
  const out = applyFilters(rows, { actor: "no-such-id", action: null, timePreset: "all" }, NOW_MS);
  assert.deepStrictEqual(out, []);
});

// ---------------------------------------------------------------------------
// Single-axis: action
// ---------------------------------------------------------------------------

test("action filter matches the raw registry key", () => {
  const out = applyFilters(rows, { actor: null, action: "add_participant", timePreset: "all" }, NOW_MS);
  assert.deepStrictEqual(out.map((r) => r.id).sort(), ["r1", "r3"]);
});

test("action filter is exact-match (no substring leak)", () => {
  const out = applyFilters(rows, { actor: null, action: "add", timePreset: "all" }, NOW_MS);
  assert.deepStrictEqual(out, []);
});

// ---------------------------------------------------------------------------
// Single-axis: timePreset
// ---------------------------------------------------------------------------

test("timePreset 1h includes only the within-hour row", () => {
  const out = applyFilters(rows, { actor: null, action: null, timePreset: "1h" }, NOW_MS);
  // r1 (-30m) and r4 (-15m) are within the last hour; nothing else is.
  assert.deepStrictEqual(out.map((r) => r.id).sort(), ["r1", "r4"]);
});

test("timePreset 24h includes hour and 3-hour rows", () => {
  const out = applyFilters(rows, { actor: null, action: null, timePreset: "24h" }, NOW_MS);
  assert.deepStrictEqual(out.map((r) => r.id).sort(), ["r1", "r2", "r4"]);
});

test("timePreset 7d includes 2-day row but not 10-day row", () => {
  const out = applyFilters(rows, { actor: null, action: null, timePreset: "7d" }, NOW_MS);
  assert.deepStrictEqual(out.map((r) => r.id).sort(), ["r1", "r2", "r3", "r4"]);
});

test("timePreset boundary: row at exactly cutoff is included", () => {
  // Build a row whose timestamp is exactly NOW - 3600s (the 1h cutoff).
  const boundaryRow = row({ id: "edge", timestamp: isoFromNow(-3600) });
  const out = applyFilters([boundaryRow], { actor: null, action: null, timePreset: "1h" }, NOW_MS);
  assert.strictEqual(out.length, 1, "row at exact cutoff must be included (>= cutoff)");
});

test("timePreset all is a no-op", () => {
  const out = applyFilters(rows, { actor: null, action: null, timePreset: "all" }, NOW_MS);
  assert.strictEqual(out.length, rows.length);
});

test("unknown timePreset key falls back to 'all'", () => {
  // Defensive default per matchesFilters - a stale persisted value
  // must not accidentally hide every row.
  const out = applyFilters(
    rows,
    { actor: null, action: null, timePreset: "1y" /* not in TIME_PRESETS */ },
    NOW_MS,
  );
  assert.strictEqual(out.length, rows.length);
});

test("rows with malformed timestamps are excluded when time filter active", () => {
  const broken = row({ id: "broken", timestamp: "not-a-date" });
  const out = applyFilters([broken], { actor: null, action: null, timePreset: "1h" }, NOW_MS);
  assert.deepStrictEqual(out, []);
});

test("rows with malformed timestamps PASS when time filter inactive", () => {
  const broken = row({ id: "broken", timestamp: "not-a-date" });
  const out = applyFilters([broken], EMPTY_FILTERS, NOW_MS);
  assert.strictEqual(out.length, 1);
});

// ---------------------------------------------------------------------------
// Multi-axis intersection
// ---------------------------------------------------------------------------

test("actor + action intersect (both must match)", () => {
  const out = applyFilters(
    rows,
    { actor: ALICE, action: "add_participant", timePreset: "all" },
    NOW_MS,
  );
  assert.deepStrictEqual(out.map((r) => r.id), ["r1"]);
});

test("actor + action + time intersect", () => {
  const out = applyFilters(
    rows,
    { actor: ALICE, action: "review_gate_approve", timePreset: "24h" },
    NOW_MS,
  );
  assert.deepStrictEqual(out.map((r) => r.id), ["r2"]);
});

test("intersection that nothing satisfies returns []", () => {
  const out = applyFilters(
    rows,
    { actor: BOB, action: "rotate_token", timePreset: "all" },
    NOW_MS,
  );
  assert.deepStrictEqual(out, []);
});

// ---------------------------------------------------------------------------
// matchesFilters individual-row contract (used by the badge counter)
// ---------------------------------------------------------------------------

test("matchesFilters true for empty filter on any row", () => {
  for (const r of rows) {
    assert.ok(matchesFilters(r, EMPTY_FILTERS, NOW_MS));
  }
});

test("matchesFilters false on null row", () => {
  assert.strictEqual(matchesFilters(null, EMPTY_FILTERS, NOW_MS), false);
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
