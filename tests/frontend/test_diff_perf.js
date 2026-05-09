#!/usr/bin/env node
/* SACP frontend perf test - audit-log diff engine (spec 029 V14 / FR-008).
 *
 * Pure-Node perf test for frontend/diff_engine.js. Run:
 *   node tests/frontend/test_diff_perf.js
 *
 * Exit code: 0 = budget met (or jsdiff unavailable -> skipped); 1 = budget exceeded.
 *
 * V14 binding contract for the <=50KB tier: P95 main-thread diffLines
 * latency MUST be <= 100ms on CI hardware (research.md §13). This test
 * generates a 50KB synthetic line-edit fixture and runs diffLinesSync
 * 20 times; the 95th percentile of those samples is asserted against
 * the budget.
 *
 * The spec intentionally treats CI hardware as the budget reference
 * (frontend perf is platform-relative). If a maintainer observes the
 * test flapping on a slow CI runner, raise the budget here in concert
 * with the FR-008 spec text rather than weakening the assertion ad hoc.
 *
 * jsdiff is sourced from scripts/node_modules so the test runs without
 * an extra install step in CI (the same install already pulls
 * @babel/parser for the JSX syntax gate).
 */

"use strict";

const path = require("path");
const assert = require("assert");

const ENGINE = require(path.join(__dirname, "..", "..", "frontend", "diff_engine.js"));

// Try to load the real jsdiff from scripts/node_modules. If the
// install step has not run (local checkout without `npm ci` in
// scripts/), skip the perf assertion with exit 0 so the test does
// not become a hard CI failure for an environment-coupled reason.
let realDiff = null;
try {
  realDiff = require(path.join(__dirname, "..", "..", "scripts", "node_modules", "diff"));
} catch (_e) {
  console.log("SKIP  diff package not installed under scripts/node_modules");
  console.log("      run `npm ci` in scripts/ to enable the perf assertion");
  process.exit(0);
}

ENGINE.setDiffLibrary(realDiff);

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
// Generate a 50KB synthetic line-edit fixture. Each line is ~50 chars; we
// emit 1000 lines for 50,000 chars. The "next" version mutates ~5% of the
// lines so the diff has real work to do (otherwise jsdiff short-circuits).
// ---------------------------------------------------------------------------

function makeFixture(byteSize, mutationRate) {
  const lineLen = 50;
  const lineCount = Math.max(1, Math.floor(byteSize / lineLen));
  const prevLines = [];
  const nextLines = [];
  for (let i = 0; i < lineCount; i += 1) {
    const base = ("line " + i + " ").padEnd(lineLen - 1, "x");
    prevLines.push(base);
    if (Math.random() < mutationRate) {
      nextLines.push(base.replace(/x/g, "y"));
    } else {
      nextLines.push(base);
    }
  }
  return { prev: prevLines.join("\n"), next: nextLines.join("\n") };
}

// ---------------------------------------------------------------------------
// Sample N runs and return P95 latency in milliseconds. perf_hooks is built
// in to Node so no extra dep is needed.
// ---------------------------------------------------------------------------

function sampleP95(fn, runs) {
  const { performance } = require("node:perf_hooks");
  const samples = [];
  for (let i = 0; i < runs; i += 1) {
    const t0 = performance.now();
    fn();
    samples.push(performance.now() - t0);
  }
  samples.sort((a, b) => a - b);
  const p95Index = Math.min(samples.length - 1, Math.floor(samples.length * 0.95));
  return samples[p95Index];
}

// ---------------------------------------------------------------------------
// Boundary correctness (assert before the latency walk so a regression in
// chooseDiffMode is the first thing to fail rather than a confusing perf flap)
// ---------------------------------------------------------------------------

test("chooseDiffMode boundary at 50,000 picks 'main'", () => {
  assert.strictEqual(ENGINE.chooseDiffMode(50000), "main");
});

test("chooseDiffMode just above 50,000 picks 'worker'", () => {
  assert.strictEqual(ENGINE.chooseDiffMode(50001), "worker");
});

// ---------------------------------------------------------------------------
// 50KB main-thread budget
// ---------------------------------------------------------------------------

test("50KB diffLinesSync P95 <= 100ms (V14 budget)", () => {
  const fixture = makeFixture(50000, 0.05);
  // Warm up jsdiff once so the V8 JIT has a hot path before measuring.
  ENGINE.diffLinesSync(fixture.prev, fixture.next, "text");
  const p95 = sampleP95(
    () => ENGINE.diffLinesSync(fixture.prev, fixture.next, "text"),
    20,
  );
  console.log("      P95 = " + p95.toFixed(2) + "ms");
  assert.ok(
    p95 <= 100,
    "P95 latency " + p95.toFixed(2) + "ms exceeds 100ms budget",
  );
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
