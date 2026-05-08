#!/usr/bin/env node
/* SACP frontend test — session-length cap configuration helpers.
 *
 * Pure-Node test for the logic in frontend/cap_config.js.
 * Run: node tests/frontend/test_025_cap_config.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "cap_config.js"));
const {
  PRESETS,
  PRESET_OPTIONS,
  getPresetValues,
  validateCustomCap,
  buildCapPayload,
  formatCountdown,
  formatBannerText,
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
// PRESETS shape
// ---------------------------------------------------------------------------

test("short preset has expected seconds and turns (FR-023)", () => {
  assert.strictEqual(PRESETS.short.seconds, 1800);
  assert.strictEqual(PRESETS.short.turns, 20);
  assert.strictEqual(PRESETS.short.kind, "both");
});

test("medium preset has expected seconds and turns (FR-023)", () => {
  assert.strictEqual(PRESETS.medium.seconds, 7200);
  assert.strictEqual(PRESETS.medium.turns, 50);
});

test("long preset has expected seconds and turns (FR-023)", () => {
  assert.strictEqual(PRESETS.long.seconds, 28800);
  assert.strictEqual(PRESETS.long.turns, 200);
});

test("none preset has null seconds and turns", () => {
  assert.strictEqual(PRESETS.none.kind, "none");
  assert.strictEqual(PRESETS.none.seconds, null);
  assert.strictEqual(PRESETS.none.turns, null);
});

test("PRESET_OPTIONS covers all four built-in presets plus custom", () => {
  const values = PRESET_OPTIONS.map((o) => o.value);
  assert.ok(values.includes("short"));
  assert.ok(values.includes("medium"));
  assert.ok(values.includes("long"));
  assert.ok(values.includes("custom"));
  assert.ok(values.includes("none"));
});

// ---------------------------------------------------------------------------
// getPresetValues
// ---------------------------------------------------------------------------

test("getPresetValues returns short preset for 'short'", () => {
  const v = getPresetValues("short");
  assert.deepStrictEqual(v, PRESETS.short);
});

test("getPresetValues is case-insensitive", () => {
  assert.deepStrictEqual(getPresetValues("SHORT"), PRESETS.short);
  assert.deepStrictEqual(getPresetValues("Long"), PRESETS.long);
});

test("getPresetValues returns none for 'custom' (caller provides own values)", () => {
  // 'custom' is not a built-in preset key → falls back to PRESETS.none
  assert.strictEqual(getPresetValues("custom"), null);
});

test("getPresetValues returns null for unknown preset", () => {
  assert.strictEqual(getPresetValues("ultra"), null);
});

// ---------------------------------------------------------------------------
// validateCustomCap
// ---------------------------------------------------------------------------

test("validateCustomCap passes for valid turns cap", () => {
  const { valid, errors } = validateCustomCap({ kind: "turns", seconds: null, turns: 20 });
  assert.strictEqual(valid, true);
  assert.strictEqual(errors.length, 0);
});

test("validateCustomCap passes for valid time cap", () => {
  const { valid } = validateCustomCap({ kind: "time", seconds: 1800, turns: null });
  assert.strictEqual(valid, true);
});

test("validateCustomCap passes for valid both cap", () => {
  const { valid } = validateCustomCap({ kind: "both", seconds: 3600, turns: 50 });
  assert.strictEqual(valid, true);
});

test("validateCustomCap passes for kind=none with null values", () => {
  const { valid } = validateCustomCap({ kind: "none", seconds: null, turns: null });
  assert.strictEqual(valid, true);
});

test("validateCustomCap rejects seconds below minimum (FR-020)", () => {
  const { valid, errors } = validateCustomCap({ kind: "time", seconds: 59, turns: null });
  assert.strictEqual(valid, false);
  assert.ok(errors.some((e) => e.includes("length_cap_seconds")));
});

test("validateCustomCap rejects turns above maximum (FR-020)", () => {
  const { valid, errors } = validateCustomCap({ kind: "turns", seconds: null, turns: 99999 });
  assert.strictEqual(valid, false);
  assert.ok(errors.some((e) => e.includes("length_cap_turns")));
});

test("validateCustomCap rejects kind=turns with missing turns (FR-022)", () => {
  const { valid, errors } = validateCustomCap({ kind: "turns", seconds: null, turns: null });
  assert.strictEqual(valid, false);
  assert.ok(errors.some((e) => e.includes("length_cap_turns is required")));
});

test("validateCustomCap rejects kind=none with non-null values (FR-022)", () => {
  const { valid, errors } = validateCustomCap({ kind: "none", seconds: 1800, turns: null });
  assert.strictEqual(valid, false);
  assert.ok(errors.some((e) => e.includes("null when kind='none'")));
});

// ---------------------------------------------------------------------------
// buildCapPayload
// ---------------------------------------------------------------------------

test("buildCapPayload for short preset produces correct body", () => {
  const body = buildCapPayload("short", null, null);
  assert.strictEqual(body.length_cap_kind, "both");
  assert.strictEqual(body.length_cap_seconds, 1800);
  assert.strictEqual(body.length_cap_turns, 20);
  assert.ok(!("interpretation" in body));
});

test("buildCapPayload for custom uses customValues", () => {
  const body = buildCapPayload("custom", { kind: "turns", seconds: null, turns: 40 }, null);
  assert.strictEqual(body.length_cap_kind, "turns");
  assert.strictEqual(body.length_cap_turns, 40);
  assert.strictEqual(body.length_cap_seconds, null);
});

test("buildCapPayload appends interpretation when supplied (re-POST path)", () => {
  const body = buildCapPayload("short", null, "absolute");
  assert.strictEqual(body.interpretation, "absolute");
});

test("buildCapPayload for none produces kind=none payload", () => {
  const body = buildCapPayload("none");
  assert.strictEqual(body.length_cap_kind, "none");
  assert.strictEqual(body.length_cap_seconds, null);
  assert.strictEqual(body.length_cap_turns, null);
});

// ---------------------------------------------------------------------------
// formatCountdown and formatBannerText
// ---------------------------------------------------------------------------

test("formatCountdown turns-only", () => {
  assert.strictEqual(formatCountdown(4, null), "4 turns");
  assert.strictEqual(formatCountdown(1, null), "1 turn");
});

test("formatCountdown seconds-only", () => {
  assert.strictEqual(formatCountdown(null, 600), "10 minutes");
  assert.strictEqual(formatCountdown(null, 60), "1 minute");
});

test("formatCountdown both dimensions", () => {
  const s = formatCountdown(4, 600);
  assert.ok(s.includes("4 turns"));
  assert.ok(s.includes("10 minutes"));
});

test("formatCountdown null/null returns empty string", () => {
  assert.strictEqual(formatCountdown(null, null), "");
});

test("formatBannerText turns-only conclude (FR-023)", () => {
  const text = formatBannerText({ turns: 4, seconds: null });
  assert.strictEqual(text, "Session is concluding — 4 turns left");
});

test("formatBannerText seconds-only conclude (FR-023)", () => {
  const text = formatBannerText({ turns: null, seconds: 300 });
  assert.strictEqual(text, "Session is concluding — 5 minutes left");
});

test("formatBannerText both null remaining", () => {
  const text = formatBannerText({ turns: null, seconds: null });
  assert.strictEqual(text, "Session is concluding");
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
