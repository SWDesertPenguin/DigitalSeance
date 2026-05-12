#!/usr/bin/env node
/* SACP frontend test - standby_ui helpers (spec 027 FR-052..FR-058 mirror).
 *
 * Pure-Node test for frontend/standby_ui.js. Exercises each pure-logic
 * helper across the inputs the React renderer in frontend/app.jsx will
 * pass at runtime.
 *
 * Run: node tests/frontend/test_standby_ui.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "standby_ui.js"));
const {
  formatWaitModeBadge,
  formatStandbyPill,
  isLongTermObserver,
  formatLongTermObserverBadge,
  isPivotMessage,
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

test("formatWaitModeBadge returns null for humans", () => {
  assert.strictEqual(
    formatWaitModeBadge({ provider: "human", wait_mode: "wait_for_human" }),
    null,
  );
});

test("formatWaitModeBadge wait_for_human", () => {
  const out = formatWaitModeBadge({ provider: "anthropic", wait_mode: "wait_for_human" });
  assert.ok(out && out.indexOf("wait for human") !== -1);
});

test("formatWaitModeBadge always", () => {
  const out = formatWaitModeBadge({ provider: "openai", wait_mode: "always" });
  assert.ok(out && out.indexOf("always") !== -1);
});

test("formatWaitModeBadge null on unknown mode", () => {
  assert.strictEqual(
    formatWaitModeBadge({ provider: "openai", wait_mode: "bogus" }),
    null,
  );
});

test("formatStandbyPill returns null when status != standby", () => {
  assert.strictEqual(formatStandbyPill({ status: "active" }, null), null);
});

test("formatStandbyPill awaiting_human", () => {
  const out = formatStandbyPill(
    { status: "standby" },
    { reason: "awaiting_human" },
  );
  assert.ok(out.indexOf("awaiting human") !== -1);
});

test("formatStandbyPill awaiting_gate", () => {
  const out = formatStandbyPill(
    { status: "standby" },
    { reason: "awaiting_gate" },
  );
  assert.ok(out.indexOf("review gate") !== -1);
});

test("formatStandbyPill filler_stuck", () => {
  const out = formatStandbyPill(
    { status: "standby" },
    { reason: "filler_stuck" },
  );
  assert.ok(out.indexOf("filler heuristic") !== -1);
});

test("isLongTermObserver true when flag set", () => {
  assert.strictEqual(
    isLongTermObserver({ wait_mode_metadata: { long_term_observer: true } }),
    true,
  );
});

test("isLongTermObserver false when flag absent", () => {
  assert.strictEqual(isLongTermObserver({ wait_mode_metadata: {} }), false);
  assert.strictEqual(isLongTermObserver({}), false);
});

test("formatLongTermObserverBadge present when flag true", () => {
  const out = formatLongTermObserverBadge({
    wait_mode_metadata: { long_term_observer: true },
  });
  assert.ok(out && out.indexOf("Long-term observer") !== -1);
});

test("formatLongTermObserverBadge null when flag false", () => {
  assert.strictEqual(
    formatLongTermObserverBadge({ wait_mode_metadata: {} }),
    null,
  );
});

test("isPivotMessage true on orchestrator_pivot metadata kind", () => {
  assert.strictEqual(
    isPivotMessage({ metadata: { kind: "orchestrator_pivot" } }),
    true,
  );
});

test("isPivotMessage false on other system message", () => {
  assert.strictEqual(
    isPivotMessage({ metadata: { kind: "summary" } }),
    false,
  );
  assert.strictEqual(isPivotMessage({ metadata: {} }), false);
  assert.strictEqual(isPivotMessage({}), false);
});

console.log("");
console.log(passed + " passed, " + failed + " failed.");
process.exit(failed === 0 ? 0 : 1);
