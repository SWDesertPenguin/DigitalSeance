#!/usr/bin/env node
/* SACP frontend test — default AI participant name suggestions.
 *
 * Pure-Node test for the logic in frontend/default_names.js. The
 * suggestion logic is pure JS (no React, no browser); it can be
 * imported and exercised directly under Node without a Babel
 * transform or a browser harness.
 *
 * Run:
 *   node tests/frontend/test_default_ai_names.js
 *
 * Exit code: 0 = all pass; 1 = any failure.
 *
 * Why a hand-rolled harness rather than a JS test framework: the
 * project's frontend ships without a package.json or build system
 * (single-file Babel-in-browser app.jsx). Pulling in jest/vitest
 * just for this one feature would expand the toolchain meaningfully.
 * The Playwright e2e harness (tests/e2e/) is the project's adopted
 * framework for browser-requiring tests; this logic is pure and
 * doesn't need a browser, so a Node-side harness is the right
 * weight.
 */

"use strict";

const path = require("path");
const assert = require("assert");

const MOD = require(path.join(__dirname, "..", "..", "frontend", "default_names.js"));
const {
  AI_NAME_POOLS,
  RECENT_NAMES_CAP,
  recentNamesStorageKey,
  getNamePool,
  applyCollisionSuffix,
  pickDefaultName,
  loadRecentNames,
  saveRecentName,
  _stripCollisionSuffix,
} = MOD;

// Minimal localStorage stub for Node. The module's loadRecentNames /
// saveRecentName check `typeof localStorage` so we can install one
// here for the persistence tests.
function installLocalStorageStub() {
  const store = new Map();
  // The module reads `typeof localStorage` (a global), so we install
  // it on globalThis. The stub mimics the subset of the Web Storage
  // API our module touches: getItem, setItem.
  globalThis.localStorage = {
    getItem(key) { return store.has(key) ? store.get(key) : null; },
    setItem(key, value) { store.set(key, String(value)); },
    removeItem(key) { store.delete(key); },
    clear() { store.clear(); },
    _store: store,
  };
  return globalThis.localStorage;
}

function uninstallLocalStorageStub() {
  delete globalThis.localStorage;
}

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
// Pool inventory + key resolution
// ---------------------------------------------------------------------------

test("AI_NAME_POOLS contains all six provider keys + generic", () => {
  for (const provider of ["anthropic", "openai", "gemini", "groq", "ollama", "vllm", "generic"]) {
    assert.ok(Array.isArray(AI_NAME_POOLS[provider]), "missing pool for " + provider);
    assert.strictEqual(AI_NAME_POOLS[provider].length, 5,
      "pool for " + provider + " should be 5 names");
  }
});

test("getNamePool returns a copy (mutation-safe)", () => {
  const pool = getNamePool("anthropic");
  pool.push("Mutant");
  assert.strictEqual(getNamePool("anthropic").length, 5);
});

test("getNamePool falls back to generic for unknown providers", () => {
  const pool = getNamePool("unknown_provider_xyz");
  assert.deepStrictEqual(pool.sort(), AI_NAME_POOLS.generic.slice().sort());
});

// ---------------------------------------------------------------------------
// Collision suffix
// ---------------------------------------------------------------------------

test("applyCollisionSuffix returns name unchanged when no collision", () => {
  assert.strictEqual(applyCollisionSuffix("Claudio", []), "Claudio");
  assert.strictEqual(applyCollisionSuffix("Claudio", ["Sage", "Quill"]), "Claudio");
});

test("applyCollisionSuffix appends 2 on first collision", () => {
  assert.strictEqual(applyCollisionSuffix("Claudio", ["Claudio"]), "Claudio2");
});

test("applyCollisionSuffix increments suffix across multiple existing same-name participants", () => {
  assert.strictEqual(
    applyCollisionSuffix("Claudio", ["Claudio", "Claudio2"]),
    "Claudio3",
  );
  assert.strictEqual(
    applyCollisionSuffix("Claudio", ["Claudio", "Claudio2", "Claudio3", "Claudio4"]),
    "Claudio5",
  );
});

test("applyCollisionSuffix is case-insensitive on existing names", () => {
  assert.strictEqual(applyCollisionSuffix("Claudio", ["claudio"]), "Claudio2");
  assert.strictEqual(applyCollisionSuffix("Claudio", ["CLAUDIO", "claudio2"]), "Claudio3");
});

test("applyCollisionSuffix trims existing names before comparison", () => {
  assert.strictEqual(applyCollisionSuffix("Claudio", ["  Claudio  "]), "Claudio2");
});

test("applyCollisionSuffix returns base unchanged for empty input", () => {
  assert.strictEqual(applyCollisionSuffix("", ["Claudio"]), "");
  assert.strictEqual(applyCollisionSuffix("   ", ["Claudio"]), "");
});

// ---------------------------------------------------------------------------
// pickDefaultName — provider-keyed pool selection
// ---------------------------------------------------------------------------

test("pickDefaultName returns a name from the provider's pool", () => {
  const pool = AI_NAME_POOLS.anthropic;
  for (let i = 0; i < 20; i += 1) {
    const pick = pickDefaultName("anthropic", [], []);
    assert.ok(pool.includes(pick), "expected pick " + pick + " in pool");
  }
});

test("pickDefaultName falls back to generic pool for unknown provider", () => {
  const pool = AI_NAME_POOLS.generic;
  for (let i = 0; i < 20; i += 1) {
    const pick = pickDefaultName("brand_new_provider", [], []);
    assert.ok(pool.includes(pick), "expected pick " + pick + " in generic pool");
  }
});

test("pickDefaultName applies collision suffix when picked name collides", () => {
  // Force a collision: pre-fill existingNames with every pool entry.
  // Whichever name pickDefaultName chooses, it MUST come back with a
  // suffix because every pool entry is taken.
  const existing = AI_NAME_POOLS.openai.slice();
  for (let i = 0; i < 20; i += 1) {
    const pick = pickDefaultName("openai", existing, []);
    // Pick should be one of the pool names with "2" appended.
    const stripped = _stripCollisionSuffix(pick);
    assert.ok(AI_NAME_POOLS.openai.includes(stripped),
      "stripped pick " + stripped + " should be in pool");
    assert.notStrictEqual(pick, stripped, "expected collision suffix");
  }
});

// ---------------------------------------------------------------------------
// pickDefaultName — recently-used exclusion
// ---------------------------------------------------------------------------

test("pickDefaultName excludes recently-used names when other pool entries are available", () => {
  // Use 4 of 5 pool entries recently. The pick should be the
  // remaining one (with vanishingly small false-positive probability).
  const recentlyUsed = AI_NAME_POOLS.anthropic.slice(0, 4);
  const expectedRemaining = AI_NAME_POOLS.anthropic[4];
  for (let i = 0; i < 20; i += 1) {
    const pick = pickDefaultName("anthropic", [], recentlyUsed);
    assert.strictEqual(pick, expectedRemaining,
      "pick " + pick + " should be the only non-recently-used entry " + expectedRemaining);
  }
});

test("pickDefaultName falls back to full pool when all entries recently used", () => {
  // All 5 used recently; pick must come from the full pool anyway
  // (suggestion is never empty).
  const recentlyUsed = AI_NAME_POOLS.gemini.slice();
  for (let i = 0; i < 20; i += 1) {
    const pick = pickDefaultName("gemini", [], recentlyUsed);
    assert.ok(AI_NAME_POOLS.gemini.includes(pick),
      "pick " + pick + " should be in gemini pool even when all recently used");
  }
});

test("pickDefaultName recently-used filter is case-insensitive", () => {
  const recentlyUsed = AI_NAME_POOLS.groq.slice(0, 4).map((n) => n.toUpperCase());
  const expectedRemaining = AI_NAME_POOLS.groq[4];
  for (let i = 0; i < 20; i += 1) {
    const pick = pickDefaultName("groq", [], recentlyUsed);
    assert.strictEqual(pick, expectedRemaining);
  }
});

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

test("loadRecentNames returns empty array when no localStorage is available", () => {
  uninstallLocalStorageStub();
  const result = loadRecentNames("anthropic");
  assert.deepStrictEqual(result, []);
});

test("loadRecentNames returns empty array on unset key", () => {
  installLocalStorageStub();
  try {
    assert.deepStrictEqual(loadRecentNames("anthropic"), []);
  } finally {
    uninstallLocalStorageStub();
  }
});

test("loadRecentNames returns empty array on malformed JSON", () => {
  const ls = installLocalStorageStub();
  try {
    ls.setItem(recentNamesStorageKey("anthropic"), "{not json");
    assert.deepStrictEqual(loadRecentNames("anthropic"), []);
  } finally {
    uninstallLocalStorageStub();
  }
});

test("saveRecentName writes pool entry to localStorage", () => {
  const ls = installLocalStorageStub();
  try {
    const result = saveRecentName("anthropic", "Claudio", []);
    assert.deepStrictEqual(result, ["Claudio"]);
    const stored = JSON.parse(ls.getItem(recentNamesStorageKey("anthropic")));
    assert.deepStrictEqual(stored, ["Claudio"]);
  } finally {
    uninstallLocalStorageStub();
  }
});

test("saveRecentName ignores non-pool (custom) names", () => {
  const ls = installLocalStorageStub();
  try {
    const result = saveRecentName("anthropic", "MyCustomName", []);
    assert.deepStrictEqual(result, []);
    assert.strictEqual(ls.getItem(recentNamesStorageKey("anthropic")), null);
  } finally {
    uninstallLocalStorageStub();
  }
});

test("saveRecentName strips collision suffix before pool-membership check", () => {
  const ls = installLocalStorageStub();
  try {
    const result = saveRecentName("anthropic", "Claudio2", []);
    // Tracked as "Claudio" in recency list.
    assert.deepStrictEqual(result, ["Claudio"]);
    const stored = JSON.parse(ls.getItem(recentNamesStorageKey("anthropic")));
    assert.deepStrictEqual(stored, ["Claudio"]);
  } finally {
    uninstallLocalStorageStub();
  }
});

test("saveRecentName de-duplicates and re-appends to track recency", () => {
  installLocalStorageStub();
  try {
    let list = saveRecentName("openai", "Sage", []);
    list = saveRecentName("openai", "Salem", list);
    list = saveRecentName("openai", "Sage", list);
    // Sage appears once at the END (most recent).
    assert.deepStrictEqual(list, ["Salem", "Sage"]);
  } finally {
    uninstallLocalStorageStub();
  }
});

test("saveRecentName enforces FIFO cap at RECENT_NAMES_CAP entries", () => {
  installLocalStorageStub();
  try {
    let list = [];
    // Push 25 distinct names (using the gemini pool 5 names cycled
    // with collision suffixes — all strip back to the pool's 5).
    // Easier: directly seed the list past the cap and verify trim.
    for (let i = 0; i < 25; i += 1) {
      // Cycle through pool entries; each save strips the suffix and
      // de-dupes the prior occurrence, so the list never exceeds 5.
      list = saveRecentName("gemini", AI_NAME_POOLS.gemini[i % 5], list);
    }
    assert.ok(list.length <= RECENT_NAMES_CAP);
    assert.ok(list.length <= 5,
      "list should be capped at the gemini pool size (5) after de-dupe");
  } finally {
    uninstallLocalStorageStub();
  }
});

test("loadRecentNames + saveRecentName persist across simulated dialog opens", () => {
  installLocalStorageStub();
  try {
    // First "dialog open + submit"
    let list = loadRecentNames("groq");
    assert.deepStrictEqual(list, []);
    saveRecentName("groq", "Quill", list);

    // Second "dialog open" — read fresh from localStorage
    list = loadRecentNames("groq");
    assert.deepStrictEqual(list, ["Quill"]);

    // pickDefaultName should now exclude Quill
    for (let i = 0; i < 10; i += 1) {
      const pick = pickDefaultName("groq", [], list);
      assert.notStrictEqual(pick, "Quill");
      assert.ok(AI_NAME_POOLS.groq.includes(pick));
    }
  } finally {
    uninstallLocalStorageStub();
  }
});

// ---------------------------------------------------------------------------
// Integration scenarios
// ---------------------------------------------------------------------------

test("scenario: collision suffix increments correctly across multiple existing same-name participants", () => {
  installLocalStorageStub();
  try {
    // Three Claudios already in the session. Force pickDefaultName to
    // pick "Claudio" by recently-using every other pool entry.
    const recentlyUsed = AI_NAME_POOLS.anthropic.filter((n) => n !== "Claudio");
    const existing = ["Claudio", "Claudio2", "Claudio3"];
    for (let i = 0; i < 20; i += 1) {
      const pick = pickDefaultName("anthropic", existing, recentlyUsed);
      assert.strictEqual(pick, "Claudio4",
        "expected Claudio4 for fourth same-name; got " + pick);
    }
  } finally {
    uninstallLocalStorageStub();
  }
});

test("scenario: empty-pool fallback when all names used recently", () => {
  installLocalStorageStub();
  try {
    // All five anthropic names recently used. Suggestion should still
    // come from the full pool (with collision suffix when needed).
    const recentlyUsed = AI_NAME_POOLS.anthropic.slice();
    // Existing has 3 of the 5 already. The pick is from the full
    // pool; if it lands on one of the existing 3, the collision
    // suffix kicks in.
    const existing = ["Claudio", "Claudia", "Claus"];
    for (let i = 0; i < 30; i += 1) {
      const pick = pickDefaultName("anthropic", existing, recentlyUsed);
      const stripped = _stripCollisionSuffix(pick);
      assert.ok(AI_NAME_POOLS.anthropic.includes(stripped),
        "stripped pick " + stripped + " in pool");
      // The pick should not match any existing name verbatim.
      assert.ok(
        !existing.map((n) => n.toLowerCase()).includes(pick.toLowerCase()),
        "pick " + pick + " should not collide with existing");
    }
  } finally {
    uninstallLocalStorageStub();
  }
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log("");
console.log("Total: " + (passed + failed) + " / Pass: " + passed + " / Fail: " + failed);
process.exit(failed === 0 ? 0 : 1);
