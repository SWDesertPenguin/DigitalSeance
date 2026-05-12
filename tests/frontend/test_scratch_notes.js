// Node-runnable test suite for frontend/scratch_notes.js (spec 024 SPA helpers).
// Mirrors the spec 022 / 029 frontend-test pattern: tiny assert harness, no
// pytest dependency, no jsdom. Invoked via `node tests/frontend/test_scratch_notes.js`.

const path = require("path");
const assert = require("assert");
const { debounceAutosave, serializeNoteUpdate, renderMarkdownSubset } =
  require(path.join(__dirname, "..", "..", "frontend", "scratch_notes.js"));

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

// ---- summary ----------------------------------------------------------------

setTimeout(function () {
  console.log("\n" + passed + " passed, " + failed + " failed");
  if (failed > 0) process.exit(1);
}, 100);
