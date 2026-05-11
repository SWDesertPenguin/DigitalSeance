#!/usr/bin/env node
/* SACP frontend test - detection-event taxonomy registry mirror (spec 022).
 *
 * Pure-Node test for frontend/detection_event_taxonomy.js.
 * Run: node tests/frontend/test_detection_event_taxonomy.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(
  path.join(__dirname, "..", "..", "frontend", "detection_event_taxonomy.js"),
);
const { EVENT_CLASSES, formatClassLabel } = MOD;

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
// Module shape
// ---------------------------------------------------------------------------

test("module exports EVENT_CLASSES and formatClassLabel", () => {
  assert.strictEqual(typeof EVENT_CLASSES, "object");
  assert.strictEqual(typeof formatClassLabel, "function");
});

test("EVENT_CLASSES contains the five v1-fixed classes (Clarifications §3 + §8)", () => {
  const expected = new Set([
    "ai_question_opened",
    "ai_exit_requested",
    "density_anomaly",
    "mode_recommendation",
    "mode_change",
  ]);
  const actual = new Set(Object.keys(EVENT_CLASSES));
  assert.strictEqual(actual.size, expected.size, "size mismatch");
  for (const key of expected) {
    assert.ok(actual.has(key), "missing key: " + key);
  }
});

test("every EVENT_CLASSES entry has a non-empty label string", () => {
  for (const key of Object.keys(EVENT_CLASSES)) {
    const entry = EVENT_CLASSES[key];
    assert.strictEqual(typeof entry, "object", key + " entry not object");
    assert.strictEqual(typeof entry.label, "string", key + " label not string");
    assert.ok(entry.label.length > 0, key + " label empty");
  }
});

// ---------------------------------------------------------------------------
// formatClassLabel
// ---------------------------------------------------------------------------

test("formatClassLabel returns registered label", () => {
  assert.strictEqual(
    formatClassLabel("ai_question_opened"),
    "AI question opened",
  );
  assert.strictEqual(
    formatClassLabel("density_anomaly"),
    "Density anomaly",
  );
  assert.strictEqual(
    formatClassLabel("mode_recommendation"),
    "Mode recommendation",
  );
});

test("formatClassLabel returns [unregistered: <key>] fallback", () => {
  assert.strictEqual(
    formatClassLabel("totally_unknown_class"),
    "[unregistered: totally_unknown_class]",
  );
});

test("formatClassLabel handles undefined / null defensively", () => {
  assert.strictEqual(
    formatClassLabel(null),
    "[unregistered: null]",
  );
  assert.strictEqual(
    formatClassLabel(undefined),
    "[unregistered: undefined]",
  );
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
