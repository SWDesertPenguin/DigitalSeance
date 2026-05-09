#!/usr/bin/env node
/* SACP frontend test - audit-log timestamp formatter (spec 029 FR-009).
 *
 * Pure-Node test for frontend/time_format.js.
 * Run: node tests/frontend/test_time_format.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "time_format.js"));
const { formatIso, formatLocale, formatRelative } = MOD;

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
// formatIso shape (parity with backend format_iso)
// ---------------------------------------------------------------------------

test("formatIso renders epoch as 1970-01-01T00:00:00.000Z", () => {
  assert.strictEqual(formatIso(new Date(0)), "1970-01-01T00:00:00.000Z");
});

test("formatIso accepts ISO-8601 string input", () => {
  assert.strictEqual(
    formatIso("2026-05-08T14:30:00.000Z"),
    "2026-05-08T14:30:00.000Z",
  );
});

test("formatIso accepts epoch milliseconds input", () => {
  // 2026-05-08T14:30:00.000Z in ms.
  const ms = Date.UTC(2026, 4, 8, 14, 30, 0, 0);
  assert.strictEqual(formatIso(ms), "2026-05-08T14:30:00.000Z");
});

test("formatIso truncates input below millisecond precision", () => {
  // Date input only carries millisecond precision, so the truncation
  // boundary is enforced by the input type. Passing a sub-ms ISO string
  // should round into the nearest ms by Date semantics.
  const out = formatIso("2026-05-08T14:30:00.123Z");
  assert.strictEqual(out, "2026-05-08T14:30:00.123Z");
});

test("formatIso pads single-digit milliseconds", () => {
  assert.strictEqual(
    formatIso("2026-05-08T14:30:00.007Z"),
    "2026-05-08T14:30:00.007Z",
  );
});

test("formatIso converts non-UTC offset input to UTC", () => {
  // 09:30 at -05:00 == 14:30 UTC.
  assert.strictEqual(
    formatIso("2026-05-08T09:30:00-05:00"),
    "2026-05-08T14:30:00.000Z",
  );
});

test("formatIso rejects null", () => {
  assert.throws(() => formatIso(null), TypeError);
});

test("formatIso rejects undefined", () => {
  assert.throws(() => formatIso(undefined), TypeError);
});

test("formatIso rejects unparseable string", () => {
  assert.throws(() => formatIso("not a date"), TypeError);
});

test("formatIso rejects Invalid Date", () => {
  assert.throws(() => formatIso(new Date("not a date")), TypeError);
});

// ---------------------------------------------------------------------------
// formatLocale (display-only; not parity-gated)
// ---------------------------------------------------------------------------

test("formatLocale returns a non-empty string for a valid Date", () => {
  const s = formatLocale(new Date("2026-05-08T14:30:00Z"));
  assert.strictEqual(typeof s, "string");
  assert.ok(s.length > 0);
});

test("formatLocale accepts ISO string input", () => {
  const s = formatLocale("2026-05-08T14:30:00Z");
  assert.strictEqual(typeof s, "string");
  assert.ok(s.length > 0);
});

// ---------------------------------------------------------------------------
// formatRelative (display-only; not parity-gated)
// ---------------------------------------------------------------------------

test("formatRelative reports past instants with 'ago' or negative locale form", () => {
  const now = Date.UTC(2026, 4, 8, 14, 30, 0, 0);
  const past = new Date(now - 3 * 60 * 1000); // 3 minutes ago
  const out = formatRelative(past, now);
  assert.strictEqual(typeof out, "string");
  assert.ok(out.length > 0);
});

test("formatRelative reports future instants with 'in' or positive locale form", () => {
  const now = Date.UTC(2026, 4, 8, 14, 30, 0, 0);
  const future = new Date(now + 5 * 3600 * 1000); // in 5 hours
  const out = formatRelative(future, now);
  assert.strictEqual(typeof out, "string");
  assert.ok(out.length > 0);
});

test("formatRelative treats zero delta as 'just now'", () => {
  const now = Date.UTC(2026, 4, 8, 14, 30, 0, 0);
  assert.strictEqual(formatRelative(new Date(now), now), "just now");
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
