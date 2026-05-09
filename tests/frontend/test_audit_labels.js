#!/usr/bin/env node
/* SACP frontend test - audit-log action-label registry mirror.
 *
 * Pure-Node test for frontend/audit_labels.js (spec 029 FR-006 mirror).
 * Run: node tests/frontend/test_audit_labels.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "audit_labels.js"));
const { LABELS, formatLabel } = MOD;

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

test("module exports LABELS and formatLabel", () => {
  assert.strictEqual(typeof LABELS, "object");
  assert.strictEqual(typeof formatLabel, "function");
});

test("LABELS contains expected v1-seed actions", () => {
  // Sample a few entries; full parity is enforced by the Python parity
  // gate (scripts/check_audit_label_parity.py).
  assert.ok("add_participant" in LABELS);
  assert.ok("review_gate_approve" in LABELS);
  assert.ok("rotate_token" in LABELS);
  assert.ok("session_config_change" in LABELS);
});

test("every LABELS entry has a non-empty label string", () => {
  for (const key of Object.keys(LABELS)) {
    const entry = LABELS[key];
    assert.strictEqual(typeof entry, "object", key + " entry not object");
    assert.strictEqual(typeof entry.label, "string", key + " label not string");
    assert.ok(entry.label.length > 0, key + " label empty");
  }
});

test("frontend mirror omits scrub_value (backend-only per FR-006)", () => {
  // Spot-check the two scrub-value actions: their entries should NOT
  // carry the flag in the frontend mirror (the SPA never sees raw
  // values for scrub-value actions; the server replaces them server-side).
  assert.ok(!("scrub_value" in LABELS["rotate_token"]));
  assert.ok(!("scrub_value" in LABELS["revoke_token"]));
});

// ---------------------------------------------------------------------------
// formatLabel
// ---------------------------------------------------------------------------

test("formatLabel returns registered label", () => {
  assert.strictEqual(
    formatLabel("add_participant"),
    "Facilitator added participant",
  );
  assert.strictEqual(
    formatLabel("review_gate_approve"),
    "Review gate: draft approved",
  );
});

test("formatLabel returns [unregistered: <action>] fallback (FR-015)", () => {
  assert.strictEqual(
    formatLabel("totally_unknown"),
    "[unregistered: totally_unknown]",
  );
});

test("formatLabel handles undefined / null defensively", () => {
  // The fallback uses String(action); null and undefined produce the
  // expected stringified form. The SPA should never call it with these
  // values, but the helper must not throw.
  assert.strictEqual(
    formatLabel(null),
    "[unregistered: null]",
  );
  assert.strictEqual(
    formatLabel(undefined),
    "[unregistered: undefined]",
  );
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
