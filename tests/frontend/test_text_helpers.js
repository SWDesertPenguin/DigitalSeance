#!/usr/bin/env node
/* SACP frontend test — text helpers (slugify + buildExportFilename).
 *
 * Pure-Node test for the logic in frontend/text_helpers.js. The
 * helpers are pure JS (no React, no browser); they import and run
 * directly under Node.
 *
 * Run:
 *   node tests/frontend/test_text_helpers.js
 *
 * Exit code: 0 = all pass; 1 = any failure.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "text_helpers.js"));
const { slugify, buildExportFilename } = MOD;

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
// slugify — alphanumeric only, hyphens collapsed, edges trimmed
// ---------------------------------------------------------------------------

test("slugify lowercases and replaces whitespace with hyphens", () => {
  assert.strictEqual(slugify("Brave Wolf c667"), "brave-wolf-c667");
  assert.strictEqual(slugify("HELLO WORLD"), "hello-world");
});

test("slugify replaces non-alphanumeric characters with hyphens", () => {
  assert.strictEqual(slugify("research/co-author"), "research-co-author");
  assert.strictEqual(slugify("a.b.c"), "a-b-c");
  assert.strictEqual(slugify("name (v2)"), "name-v2");
});

test("slugify collapses multiple consecutive separators into one hyphen", () => {
  assert.strictEqual(slugify("hello   world"), "hello-world");
  assert.strictEqual(slugify("a___b"), "a-b");
  assert.strictEqual(slugify("foo / / bar"), "foo-bar");
  assert.strictEqual(slugify("mixed   _ - punctuation!@# end"), "mixed-punctuation-end");
});

test("slugify trims hyphens from both edges", () => {
  assert.strictEqual(slugify("---foo---"), "foo");
  assert.strictEqual(slugify("  hello  "), "hello");
  assert.strictEqual(slugify("/leading/slash/"), "leading-slash");
});

test("slugify strips non-ASCII characters", () => {
  // Per the brief's standard pattern, non-alphanumeric (including
  // non-ASCII letters) gets replaced. Operators with Unicode session
  // names get the ASCII-safe surface for filenames.
  assert.strictEqual(slugify("ünicode!ish ✓"), "nicode-ish");
});

test("slugify handles empty input by returning empty string", () => {
  assert.strictEqual(slugify(""), "");
  assert.strictEqual(slugify(null), "");
  assert.strictEqual(slugify(undefined), "");
});

test("slugify handles input that's entirely non-alphanumeric", () => {
  // Returning empty allows callers to detect "no usable name" and
  // fall through to the generic.
  assert.strictEqual(slugify("!!!"), "");
  assert.strictEqual(slugify("   "), "");
  assert.strictEqual(slugify("---"), "");
});

test("slugify preserves digits and is idempotent", () => {
  assert.strictEqual(slugify("session-123"), "session-123");
  assert.strictEqual(slugify(slugify("Brave Wolf c667")), "brave-wolf-c667");
});

// ---------------------------------------------------------------------------
// buildExportFilename — session name → filename with extension
// ---------------------------------------------------------------------------

test("filename generation: slugified session name plus extension", () => {
  assert.strictEqual(
    buildExportFilename("Brave Wolf c667", "markdown", "fallback"),
    "brave-wolf-c667.md",
  );
  assert.strictEqual(
    buildExportFilename("Brave Wolf c667", "json", "fallback"),
    "brave-wolf-c667.json",
  );
});

test("filename generation: handles arbitrary special chars in session name", () => {
  assert.strictEqual(
    buildExportFilename("research / co-author 2026", "markdown", "fallback"),
    "research-co-author-2026.md",
  );
  assert.strictEqual(
    buildExportFilename("Karen's chat (#1)", "markdown", "fallback"),
    "karen-s-chat-1.md",
  );
});

test("filename fallback: empty session name falls through to generic", () => {
  // The existing fallback shape `sacp-<uuid>-<ts>` already has no
  // extension; buildExportFilename appends one when needed.
  assert.strictEqual(
    buildExportFilename("", "markdown", "sacp-abc-1234567890"),
    "sacp-abc-1234567890.md",
  );
  assert.strictEqual(
    buildExportFilename(null, "json", "sacp-abc-1234567890"),
    "sacp-abc-1234567890.json",
  );
  assert.strictEqual(
    buildExportFilename(undefined, "markdown", "sacp-abc-1234567890"),
    "sacp-abc-1234567890.md",
  );
});

test("filename fallback: name that slugifies to empty also falls through", () => {
  assert.strictEqual(
    buildExportFilename("!!!", "markdown", "sacp-abc-1234567890"),
    "sacp-abc-1234567890.md",
  );
  assert.strictEqual(
    buildExportFilename("   ", "json", "sacp-abc-1234567890"),
    "sacp-abc-1234567890.json",
  );
});

test("filename fallback: avoids double-extension when fallback already has it", () => {
  assert.strictEqual(
    buildExportFilename("", "markdown", "sacp-abc-1234567890.md"),
    "sacp-abc-1234567890.md",
  );
  assert.strictEqual(
    buildExportFilename("", "json", "Sacp-abc.JSON"),
    "Sacp-abc.JSON",
    "case-insensitive match avoids double-ext",
  );
});

test("filename fallback: no fallback provided gives generic export.<ext>", () => {
  assert.strictEqual(buildExportFilename("", "markdown", null), "export.md");
  assert.strictEqual(buildExportFilename(null, "json", undefined), "export.json");
});

test("filename: arbitrary format strings used as extension verbatim", () => {
  assert.strictEqual(
    buildExportFilename("test session", "csv", "fallback"),
    "test-session.csv",
  );
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
