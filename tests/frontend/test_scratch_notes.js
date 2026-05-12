// Node-runnable test suite for frontend/scratch_notes.js (spec 024 SPA helpers).
// Mirrors the spec 022 / 029 frontend-test pattern: tiny assert harness, no
// pytest dependency, no jsdom. Invoked via `node tests/frontend/test_scratch_notes.js`.

const path = require("path");
const assert = require("assert");
const {
  debounceAutosave,
  serializeNoteUpdate,
  renderMarkdownSubset,
  describeScope,
  formatPromotedMarker,
  parseSummaryContent,
  formatTurnRange,
  reviewGateDisposition,
} = require(path.join(__dirname, "..", "..", "frontend", "scratch_notes.js"));

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log("PASS " + name);
  } catch (e) {
    failed++;
    console.error("FAIL " + name);
    console.error("  " + (e && e.message ? e.message : e));
  }
}

// ---- debounceAutosave -------------------------------------------------------

test("debounceAutosave defers calls until wait elapses", function (done) {
  let calls = 0;
  const trigger = debounceAutosave(function () { calls++; }, 10);
  trigger("a"); trigger("b"); trigger("c");
  setTimeout(function () {
    assert.strictEqual(calls, 1, "expected one batched call, got " + calls);
  }, 25);
});

test("debounceAutosave.pending reports timer state", function () {
  const trigger = debounceAutosave(function () {}, 50);
  assert.strictEqual(trigger.pending(), false);
  trigger();
  assert.strictEqual(trigger.pending(), true);
  trigger.cancel();
  assert.strictEqual(trigger.pending(), false);
});

test("debounceAutosave.cancel suppresses pending fire", function () {
  let calls = 0;
  const trigger = debounceAutosave(function () { calls++; }, 5);
  trigger();
  trigger.cancel();
  setTimeout(function () {
    assert.strictEqual(calls, 0);
  }, 15);
});

test("debounceAutosave throws on non-function", function () {
  assert.throws(function () { debounceAutosave(null, 10); }, TypeError);
});

// ---- serializeNoteUpdate ----------------------------------------------------

test("serializeNoteUpdate returns content + version", function () {
  const out = serializeNoteUpdate({ content: "hello", version: 3, extra: 1 });
  assert.deepStrictEqual(out, { content: "hello", version: 3 });
});

test("serializeNoteUpdate rejects missing content", function () {
  assert.throws(function () {
    serializeNoteUpdate({ version: 1 });
  }, TypeError);
});

test("serializeNoteUpdate rejects version < 1", function () {
  assert.throws(function () {
    serializeNoteUpdate({ content: "x", version: 0 });
  }, TypeError);
});

// ---- renderMarkdownSubset ---------------------------------------------------

test("renderMarkdownSubset escapes HTML in plain text", function () {
  const out = renderMarkdownSubset("<script>x</script>");
  assert.ok(out.includes("&lt;script&gt;"));
  assert.ok(!out.includes("<script>"));
});

test("renderMarkdownSubset renders bold + italic + code", function () {
  const out = renderMarkdownSubset("**bold** *italic* `code`");
  assert.ok(out.includes("<strong>bold</strong>"));
  assert.ok(out.includes("<em>italic</em>"));
  assert.ok(out.includes("<code>code</code>"));
});

test("renderMarkdownSubset renders headings up to level 6", function () {
  for (let n = 1; n <= 6; n++) {
    const hashes = "#".repeat(n);
    const out = renderMarkdownSubset(hashes + " Title");
    assert.ok(out.includes("<h" + n + ">Title</h" + n + ">"));
  }
});

test("renderMarkdownSubset renders bullet lists", function () {
  const out = renderMarkdownSubset("- one\n- two\n- three");
  assert.ok(out.includes("<ul>"));
  assert.ok(out.includes("<li>one</li>"));
  assert.ok(out.includes("<li>two</li>"));
  assert.ok(out.includes("<li>three</li>"));
  assert.ok(out.includes("</ul>"));
});

test("renderMarkdownSubset renders code blocks", function () {
  const out = renderMarkdownSubset("```\nx = 1\n```");
  assert.ok(out.includes("<pre><code>"));
  assert.ok(out.includes("x = 1"));
});

test("renderMarkdownSubset renders links only for http(s) URLs", function () {
  const httpOut = renderMarkdownSubset("[github](https://github.com)");
  assert.ok(httpOut.includes('href="https://github.com"'));
  const javascriptOut = renderMarkdownSubset("[bad](javascript:alert(1))");
  assert.ok(!javascriptOut.includes("<a "), "javascript: URL must not render as <a> tag");
});

test("renderMarkdownSubset returns empty string for non-string input", function () {
  assert.strictEqual(renderMarkdownSubset(null), "");
  assert.strictEqual(renderMarkdownSubset(undefined), "");
});

// ---- describeScope ----------------------------------------------------------

test("describeScope returns account chip + explanation for account scope", function () {
  const out = describeScope("account");
  assert.strictEqual(out.chipText, "Account-scoped");
  assert.ok(out.chipClass.includes("account"));
  assert.ok(out.explanation.toLowerCase().includes("survive"));
});

test("describeScope returns session chip + warning for session scope", function () {
  const out = describeScope("session");
  assert.strictEqual(out.chipText, "Session-scoped");
  assert.ok(out.chipClass.includes("session"));
  assert.ok(out.explanation.toLowerCase().includes("deleted"));
});

test("describeScope defaults to session for missing/unknown values", function () {
  assert.strictEqual(describeScope(null).chipText, "Session-scoped");
  assert.strictEqual(describeScope(undefined).chipText, "Session-scoped");
  assert.strictEqual(describeScope("garbage").chipText, "Session-scoped");
});

// ---- formatPromotedMarker ---------------------------------------------------

test("formatPromotedMarker returns null for un-promoted notes", function () {
  assert.strictEqual(formatPromotedMarker({ promoted_at: null }), null);
  assert.strictEqual(formatPromotedMarker({}), null);
  assert.strictEqual(formatPromotedMarker(null), null);
});

test("formatPromotedMarker captures turn + timestamp for promoted notes", function () {
  const out = formatPromotedMarker({
    promoted_at: "2026-05-12T10:00:00Z",
    promoted_message_turn: 47,
  });
  assert.strictEqual(out.promoted, true);
  assert.strictEqual(out.turn, 47);
  assert.strictEqual(out.promotedAt, "2026-05-12T10:00:00Z");
});

// ---- parseSummaryContent ----------------------------------------------------

test("parseSummaryContent extracts four structured sections from valid JSON", function () {
  const raw = JSON.stringify({
    narrative: "We discussed X.",
    decisions: ["d1", "d2"],
    open_questions: ["q1"],
    key_positions: [{ participant: "Alice", position: "yes" }],
  });
  const out = parseSummaryContent(raw);
  assert.strictEqual(out.narrative, "We discussed X.");
  assert.deepStrictEqual(out.decisions, ["d1", "d2"]);
  assert.deepStrictEqual(out.open_questions, ["q1"]);
  assert.strictEqual(out.key_positions.length, 1);
});

test("parseSummaryContent falls back to raw narrative on parse failure", function () {
  const out = parseSummaryContent("not valid json {{{");
  assert.strictEqual(out.narrative, "not valid json {{{");
  assert.deepStrictEqual(out.decisions, []);
});

test("parseSummaryContent returns empty shape for null / empty input", function () {
  const out = parseSummaryContent(null);
  assert.strictEqual(out.narrative, "");
  assert.deepStrictEqual(out.decisions, []);
});

// ---- formatTurnRange --------------------------------------------------------

test("formatTurnRange returns single turn when only one summary", function () {
  assert.strictEqual(formatTurnRange({ turn_number: 5 }, null), "turn 1-5");
});

test("formatTurnRange returns inclusive range between summaries", function () {
  assert.strictEqual(formatTurnRange({ turn_number: 96 }, { turn_number: 46 }), "turn 47-96");
});

test("formatTurnRange handles missing turn_number gracefully", function () {
  assert.strictEqual(formatTurnRange(null, null), "");
  assert.strictEqual(formatTurnRange({}, null), "");
});

// ---- reviewGateDisposition --------------------------------------------------

test("reviewGateDisposition maps action keys to friendly labels", function () {
  assert.strictEqual(reviewGateDisposition("review_gate_approve"), "Approved (verbatim)");
  assert.strictEqual(reviewGateDisposition("review_gate_edit"), "Approved (edited)");
  assert.strictEqual(reviewGateDisposition("review_gate_reject"), "Rejected");
  assert.strictEqual(reviewGateDisposition("unknown_action"), "unknown_action");
});

// ---- summary ----------------------------------------------------------------

setTimeout(function () {
  console.log("\n" + passed + " passed, " + failed + " failed");
  if (failed > 0) process.exit(1);
}, 100);
