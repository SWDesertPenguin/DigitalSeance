#!/usr/bin/env node
/* SACP frontend test - audit-log diff engine (spec 029 FR-008 / US2).
 *
 * Pure-Node test for frontend/diff_engine.js. Run:
 *   node tests/frontend/test_diff_engine.js
 *
 * Exit code: 0 = all pass; 1 = any failure.
 *
 * The engine resolves jsdiff lazily; in the browser it picks up
 * window.Diff from the CDN <script>. Here we inject a small stub
 * via setDiffLibrary() so the test stays free of npm dependencies.
 * The stub mirrors the jsdiff change-array shape but uses simple
 * line/word splits — sufficient to verify the engine's dispatch
 * logic, format probing, and JSON-vs-text routing.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const ENGINE = require(path.join(__dirname, "..", "..", "frontend", "diff_engine.js"));
const {
  MAIN_THREAD_BYTE_THRESHOLD,
  WORKER_BYTE_THRESHOLD,
  chooseDiffMode,
  diffLinesSync,
  diffWordsSync,
  setDiffLibrary,
  _maxByteSize,
} = ENGINE;

// jsdiff stub. Records which method was called so the format-probe
// tests can assert on routing without inspecting the change array.
let lastCall = null;
const stubDiff = {
  diffLines(prev, next) {
    lastCall = { method: "diffLines", prev: prev, next: next };
    if (prev === next) return [{ value: prev, count: 1 }];
    return [
      { value: prev, count: 1, removed: true },
      { value: next, count: 1, added: true },
    ];
  },
  diffWords(prev, next) {
    lastCall = { method: "diffWords", prev: prev, next: next };
    if (prev === next) return [{ value: prev, count: 1 }];
    return [
      { value: prev, count: 1, removed: true },
      { value: next, count: 1, added: true },
    ];
  },
  diffJson(prev, next) {
    lastCall = { method: "diffJson", prev: prev, next: next };
    return [
      { value: JSON.stringify(prev), count: 1, removed: true },
      { value: JSON.stringify(next), count: 1, added: true },
    ];
  },
};

setDiffLibrary(stubDiff);

let passed = 0;
let failed = 0;

function test(name, fn) {
  lastCall = null;
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
// Module shape + locked threshold constants
// ---------------------------------------------------------------------------

test("module exports the locked threshold constants", () => {
  assert.strictEqual(MAIN_THREAD_BYTE_THRESHOLD, 50000);
  assert.strictEqual(WORKER_BYTE_THRESHOLD, 500000);
});

test("module exports the public surface", () => {
  assert.strictEqual(typeof chooseDiffMode, "function");
  assert.strictEqual(typeof diffLinesSync, "function");
  assert.strictEqual(typeof diffWordsSync, "function");
  assert.strictEqual(typeof ENGINE.diffLinesViaWorker, "function");
  assert.strictEqual(typeof setDiffLibrary, "function");
});

// ---------------------------------------------------------------------------
// chooseDiffMode threshold transitions
// ---------------------------------------------------------------------------

test("chooseDiffMode returns 'main' below 50,000", () => {
  assert.strictEqual(chooseDiffMode(0), "main");
  assert.strictEqual(chooseDiffMode(1), "main");
  assert.strictEqual(chooseDiffMode(49999), "main");
  assert.strictEqual(chooseDiffMode(50000), "main");
});

test("chooseDiffMode returns 'worker' between 50,001 and 500,000", () => {
  assert.strictEqual(chooseDiffMode(50001), "worker");
  assert.strictEqual(chooseDiffMode(100000), "worker");
  assert.strictEqual(chooseDiffMode(500000), "worker");
});

test("chooseDiffMode returns 'raw' above 500,000", () => {
  assert.strictEqual(chooseDiffMode(500001), "raw");
  assert.strictEqual(chooseDiffMode(1000000), "raw");
});

// ---------------------------------------------------------------------------
// _maxByteSize
// ---------------------------------------------------------------------------

test("_maxByteSize handles null + undefined as zero", () => {
  assert.strictEqual(_maxByteSize(null, null), 0);
  assert.strictEqual(_maxByteSize(undefined, undefined), 0);
  assert.strictEqual(_maxByteSize(null, "abc"), 3);
  assert.strictEqual(_maxByteSize("abc", null), 3);
});

test("_maxByteSize returns the larger length", () => {
  assert.strictEqual(_maxByteSize("abc", "abcdef"), 6);
  assert.strictEqual(_maxByteSize("abcdef", "abc"), 6);
  assert.strictEqual(_maxByteSize("equal", "equal"), 5);
});

// ---------------------------------------------------------------------------
// diffLinesSync routing (format autodetect)
// ---------------------------------------------------------------------------

test("diffLinesSync(format='text') always uses diffLines", () => {
  const out = diffLinesSync("a\nb\n", "a\nc\n", "text");
  assert.strictEqual(lastCall.method, "diffLines");
  assert.ok(Array.isArray(out));
});

test("diffLinesSync(format='json') always uses diffJson", () => {
  const out = diffLinesSync('{"a":1}', '{"a":2}', "json");
  assert.strictEqual(lastCall.method, "diffJson");
  assert.deepStrictEqual(lastCall.prev, { a: 1 });
  assert.deepStrictEqual(lastCall.next, { a: 2 });
  assert.ok(Array.isArray(out));
});

test("diffLinesSync(format='auto') with both-JSON inputs uses diffJson", () => {
  diffLinesSync('{"a":1}', '{"a":2}', "auto");
  assert.strictEqual(lastCall.method, "diffJson");
});

test("diffLinesSync(format='auto') with non-JSON falls back to diffLines", () => {
  diffLinesSync("plain text", "other text", "auto");
  assert.strictEqual(lastCall.method, "diffLines");
});

test("diffLinesSync(format='auto') with one-side non-JSON uses diffLines", () => {
  diffLinesSync('{"a":1}', "not json", "auto");
  assert.strictEqual(lastCall.method, "diffLines");
});

test("diffLinesSync default format is 'auto'", () => {
  diffLinesSync('{"a":1}', '{"a":2}');
  assert.strictEqual(lastCall.method, "diffJson");
});

test("diffLinesSync handles null inputs as empty strings", () => {
  diffLinesSync(null, "x", "text");
  assert.strictEqual(lastCall.prev, "");
  assert.strictEqual(lastCall.next, "x");
});

// ---------------------------------------------------------------------------
// diffWordsSync
// ---------------------------------------------------------------------------

test("diffWordsSync routes through diffWords", () => {
  diffWordsSync("hello world", "hello earth");
  assert.strictEqual(lastCall.method, "diffWords");
  assert.strictEqual(lastCall.prev, "hello world");
  assert.strictEqual(lastCall.next, "hello earth");
});

test("diffWordsSync handles null inputs as empty strings", () => {
  diffWordsSync(null, null);
  assert.strictEqual(lastCall.prev, "");
  assert.strictEqual(lastCall.next, "");
});

// ---------------------------------------------------------------------------
// Library-resolution failure mode
// ---------------------------------------------------------------------------

test("missing diff library throws a clear error", () => {
  setDiffLibrary(null);
  // Also clear globalThis.Diff for this test in case anything pre-set it.
  const prior = globalThis.Diff;
  delete globalThis.Diff;
  try {
    assert.throws(
      () => diffLinesSync("a", "b", "text"),
      /jsdiff library not loaded/,
    );
  } finally {
    setDiffLibrary(stubDiff);
    if (prior) globalThis.Diff = prior;
  }
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
