#!/usr/bin/env node
/* SACP frontend test — cap-decrease disambiguation modal helpers.
 *
 * Pure-Node test for the logic in frontend/cap_disambiguation.js.
 * Run: node tests/frontend/test_025_cap_disambiguation.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "cap_disambiguation.js"));
const {
  parseDisambiguation409,
  isDisambiguation409,
  buildRepostBody,
  formatOptionLabel,
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

// Shared example 409 body matching the contract in
// contracts/cap-set-endpoint.md.
const EXAMPLE_409 = {
  error: "cap_decrease_requires_interpretation",
  current_elapsed: { turns: 30, seconds: 0 },
  submitted: { length_cap_kind: "turns", length_cap_seconds: null, length_cap_turns: 20 },
  options: {
    absolute: {
      effective_cap_turns: 20,
      effective_cap_seconds: null,
      consequence: "immediate_conclude_phase",
    },
    relative: {
      effective_cap_turns: 50,
      effective_cap_seconds: null,
      consequence: "loop_continues_until_trigger",
    },
  },
};

// ---------------------------------------------------------------------------
// isDisambiguation409
// ---------------------------------------------------------------------------

test("isDisambiguation409 returns true for valid 409 body", () => {
  assert.strictEqual(isDisambiguation409(EXAMPLE_409), true);
});

test("isDisambiguation409 returns false for non-409 error body", () => {
  assert.strictEqual(isDisambiguation409({ error: "facilitator_only" }), false);
  assert.strictEqual(isDisambiguation409(null), false);
  assert.strictEqual(isDisambiguation409("string"), false);
  assert.strictEqual(isDisambiguation409({}), false);
});

// ---------------------------------------------------------------------------
// parseDisambiguation409
// ---------------------------------------------------------------------------

test("parseDisambiguation409 returns structured model from 409 body", () => {
  const model = parseDisambiguation409(EXAMPLE_409);
  assert.ok(model !== null);
  assert.deepStrictEqual(model.currentElapsed, { turns: 30, seconds: 0 });
  assert.strictEqual(model.options.absolute.effective_cap_turns, 20);
  assert.strictEqual(model.options.relative.effective_cap_turns, 50);
});

test("parseDisambiguation409 returns null for non-disambiguation response", () => {
  assert.strictEqual(parseDisambiguation409({ error: "other_error" }), null);
  assert.strictEqual(parseDisambiguation409(null), null);
  assert.strictEqual(parseDisambiguation409(undefined), null);
});

test("parseDisambiguation409 surfaces submitted field", () => {
  const model = parseDisambiguation409(EXAMPLE_409);
  assert.strictEqual(model.submitted.length_cap_turns, 20);
});

// ---------------------------------------------------------------------------
// buildRepostBody
// ---------------------------------------------------------------------------

test("buildRepostBody appends interpretation=absolute to original body", () => {
  const orig = { length_cap_kind: "turns", length_cap_turns: 20, length_cap_seconds: null };
  const body = buildRepostBody(orig, "absolute");
  assert.strictEqual(body.interpretation, "absolute");
  assert.strictEqual(body.length_cap_turns, 20);
  assert.strictEqual(body.length_cap_kind, "turns");
});

test("buildRepostBody appends interpretation=relative to original body", () => {
  const orig = { length_cap_kind: "turns", length_cap_turns: 20, length_cap_seconds: null };
  const body = buildRepostBody(orig, "relative");
  assert.strictEqual(body.interpretation, "relative");
});

test("buildRepostBody does not mutate the original body", () => {
  const orig = { length_cap_kind: "turns", length_cap_turns: 20 };
  buildRepostBody(orig, "absolute");
  assert.ok(!("interpretation" in orig));
});

test("buildRepostBody throws on invalid interpretation", () => {
  const orig = { length_cap_kind: "turns", length_cap_turns: 20 };
  assert.throws(() => buildRepostBody(orig, "maybe"), /absolute.*relative/i);
});

test("buildRepostBody handles null original gracefully", () => {
  const body = buildRepostBody(null, "absolute");
  assert.deepStrictEqual(body, {});
});

// ---------------------------------------------------------------------------
// formatOptionLabel
// ---------------------------------------------------------------------------

test("formatOptionLabel absolute option: shows effective cap and consequence", () => {
  const label = formatOptionLabel(
    EXAMPLE_409.options.absolute,
    "absolute"
  );
  assert.ok(label.includes("20 total turns"));
  assert.ok(label.includes("conclude phase starts now"));
});

test("formatOptionLabel relative option: shows effective cap and session-start framing", () => {
  const label = formatOptionLabel(
    EXAMPLE_409.options.relative,
    "relative"
  );
  assert.ok(label.includes("50 total turns"));
  assert.ok(label.includes("from session start"));
});

test("formatOptionLabel handles missing option gracefully", () => {
  assert.strictEqual(formatOptionLabel(null, "absolute"), "");
  assert.strictEqual(formatOptionLabel(undefined, "relative"), "");
});

// ---------------------------------------------------------------------------
// Integration: full disambiguation flow
// ---------------------------------------------------------------------------

test("integration: receive 409 → parse → pick absolute → build re-POST body", () => {
  // Simulate receiving a 409 response.
  const responseBody = EXAMPLE_409;
  assert.strictEqual(isDisambiguation409(responseBody), true);

  const model = parseDisambiguation409(responseBody);
  assert.ok(model, "should parse successfully");

  // Facilitator picks 'absolute'.
  const origBody = {
    length_cap_kind: model.submitted.length_cap_kind,
    length_cap_seconds: model.submitted.length_cap_seconds,
    length_cap_turns: model.submitted.length_cap_turns,
  };
  const repostBody = buildRepostBody(origBody, "absolute");
  assert.strictEqual(repostBody.interpretation, "absolute");
  assert.strictEqual(repostBody.length_cap_turns, 20);
  assert.strictEqual(repostBody.length_cap_kind, "turns");
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
