#!/usr/bin/env node
/* SACP frontend test - detection-event history pure-logic helpers (spec 022).
 *
 * Pure-Node test for frontend/detection_history_filters.js.
 * Run: node tests/frontend/test_detection_history_filters.js
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(
  path.join(__dirname, "..", "..", "frontend", "detection_history_filters.js"),
);
const {
  defaultFilters,
  applyFilters,
  hiddenByAxis,
  sortEvents,
  truncateSnippet,
  distinctParticipants,
  TRIGGER_SNIPPET_DISPLAY_CAP,
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

function makeEvents() {
  return [
    {
      event_id: 1,
      event_class: "ai_question_opened",
      participant_id: "p1",
      timestamp: "2026-05-11T10:00:00.000Z",
      disposition: "pending",
    },
    {
      event_id: 2,
      event_class: "ai_exit_requested",
      participant_id: "p2",
      timestamp: "2026-05-11T10:05:00.000Z",
      disposition: "banner_dismissed",
    },
    {
      event_id: 3,
      event_class: "density_anomaly",
      participant_id: "p1",
      timestamp: "2026-05-11T10:10:00.000Z",
      disposition: "auto_resolved",
    },
    {
      event_id: 4,
      event_class: "mode_recommendation",
      participant_id: "facilitator1",
      timestamp: "2026-05-11T10:15:00.000Z",
      disposition: "pending",
    },
    {
      event_id: 5,
      event_class: "mode_change",
      participant_id: "facilitator1",
      timestamp: "2026-05-11T10:20:00.000Z",
      disposition: "banner_acknowledged",
    },
  ];
}

// ---------------------------------------------------------------------------
// defaultFilters
// ---------------------------------------------------------------------------

test("defaultFilters returns all-axes-all baseline", () => {
  const f = defaultFilters();
  assert.strictEqual(f.type, "all");
  assert.strictEqual(f.participant, "all");
  assert.strictEqual(f.timeRange, "all");
  assert.strictEqual(f.disposition, "all");
});

// ---------------------------------------------------------------------------
// applyFilters (AND composition)
// ---------------------------------------------------------------------------

test("applyFilters with defaults returns all events", () => {
  const out = applyFilters(makeEvents(), defaultFilters());
  assert.strictEqual(out.length, 5);
});

test("applyFilters by type narrows to matching class", () => {
  const out = applyFilters(
    makeEvents(), { ...defaultFilters(), type: "density_anomaly" },
  );
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].event_id, 3);
});

test("applyFilters by participant narrows to matching participant", () => {
  const out = applyFilters(
    makeEvents(), { ...defaultFilters(), participant: "p1" },
  );
  assert.strictEqual(out.length, 2);
});

test("applyFilters by disposition narrows to matching disposition", () => {
  const out = applyFilters(
    makeEvents(), { ...defaultFilters(), disposition: "banner_dismissed" },
  );
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].event_id, 2);
});

test("applyFilters AND composition across type + disposition", () => {
  const out = applyFilters(makeEvents(), {
    ...defaultFilters(),
    type: "mode_change",
    disposition: "banner_acknowledged",
  });
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].event_id, 5);
});

test("applyFilters with custom time-range bound", () => {
  const out = applyFilters(makeEvents(), {
    ...defaultFilters(),
    timeRange: { fromIso: "2026-05-11T10:10:00.000Z" },
  });
  assert.strictEqual(out.length, 3);
});

test("applyFilters yields empty when filter excludes all", () => {
  const out = applyFilters(makeEvents(), {
    ...defaultFilters(),
    type: "ai_question_opened",
    disposition: "banner_acknowledged",
  });
  assert.strictEqual(out.length, 0);
});

// ---------------------------------------------------------------------------
// hiddenByAxis
// ---------------------------------------------------------------------------

test("hiddenByAxis returns per-axis exclusion counts", () => {
  const counts = hiddenByAxis(makeEvents(), {
    ...defaultFilters(),
    type: "density_anomaly",
    disposition: "auto_resolved",
  });
  // 4 events excluded by type filter; 4 by disposition filter.
  assert.strictEqual(counts.type, 4);
  assert.strictEqual(counts.disposition, 4);
  assert.strictEqual(counts.participant, 0);
  assert.strictEqual(counts.timeRange, 0);
});

test("hiddenByAxis returns zeros at all-axes-all", () => {
  const counts = hiddenByAxis(makeEvents(), defaultFilters());
  assert.strictEqual(counts.type, 0);
  assert.strictEqual(counts.participant, 0);
  assert.strictEqual(counts.timeRange, 0);
  assert.strictEqual(counts.disposition, 0);
});

// ---------------------------------------------------------------------------
// sortEvents
// ---------------------------------------------------------------------------

test("sortEvents desc orders newest-first by default", () => {
  const out = sortEvents(makeEvents(), "desc");
  assert.strictEqual(out[0].event_id, 5);
  assert.strictEqual(out[4].event_id, 1);
});

test("sortEvents asc orders oldest-first", () => {
  const out = sortEvents(makeEvents(), "asc");
  assert.strictEqual(out[0].event_id, 1);
  assert.strictEqual(out[4].event_id, 5);
});

// ---------------------------------------------------------------------------
// truncateSnippet
// ---------------------------------------------------------------------------

test("truncateSnippet keeps short snippets intact", () => {
  const out = truncateSnippet("hello");
  assert.strictEqual(out.display, "hello");
  assert.strictEqual(out.truncated, false);
});

test("truncateSnippet truncates long snippets at the display cap", () => {
  const long = "x".repeat(TRIGGER_SNIPPET_DISPLAY_CAP + 50);
  const out = truncateSnippet(long);
  assert.strictEqual(out.display.length, TRIGGER_SNIPPET_DISPLAY_CAP);
  assert.strictEqual(out.full.length, long.length);
  assert.strictEqual(out.truncated, true);
});

test("truncateSnippet handles null/undefined", () => {
  assert.strictEqual(truncateSnippet(null).truncated, false);
  assert.strictEqual(truncateSnippet(undefined).truncated, false);
});

// ---------------------------------------------------------------------------
// distinctParticipants
// ---------------------------------------------------------------------------

test("distinctParticipants extracts unique participant ids sorted", () => {
  const out = distinctParticipants(makeEvents());
  assert.deepStrictEqual(out, ["facilitator1", "p1", "p2"]);
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
