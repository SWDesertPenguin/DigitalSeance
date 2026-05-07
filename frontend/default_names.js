/* SACP Web UI — default AI participant name suggestions.
 *
 * Pure-logic module loaded ahead of app.jsx via <script> in index.html.
 * UMD-style export so the same file runs unchanged in the browser
 * (attaches to window) AND in Node (CommonJS module.exports) for tests.
 *
 * The browser path is the production code; the Node path is purely so
 * tests/test_default_ai_names.js can exercise the helpers without a
 * browser harness — Playwright e2e is the project's adopted framework
 * for browser-requiring tests, but the suggestion logic is pure and
 * testable in Node directly.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Provider-keyed name pools. 5 names per provider; a mix of styles so
  // the suggestion has variety without requiring localization. Operators
  // can always rename.
  const AI_NAME_POOLS = {
    anthropic: ["Claudio", "Claudia", "Claus", "Claudette", "Claud"],
    openai:    ["Sage", "Salem", "Saga", "Sigi", "Sol"],
    gemini:    ["Gemma", "Gem", "Geminus", "Jem", "Jemma"],
    groq:      ["Quill", "Quinn", "Quark", "Quincy", "Que"],
    ollama:    ["Ollie", "Otto", "Ona", "Os", "Owen"],
    vllm:      ["Val", "Vee", "Vex", "Vio", "Vance"],
    // OpenAI-compatible / generic fallback for self-hosted gateways and
    // anything else not in the recognized provider list.
    generic:   ["Alex", "Bea", "Cy", "Dee", "Echo"],
  };

  const RECENT_NAMES_CAP = 20;
  const RECENT_NAMES_STORAGE_PREFIX = "sacp.recent-ai-names.";

  function recentNamesStorageKey(provider) {
    return RECENT_NAMES_STORAGE_PREFIX + String(provider || "generic");
  }

  // Resolve provider → pool key. Anything unrecognised falls back to
  // the generic pool so the dialog never presents an empty suggestion.
  function _resolvePoolKey(provider) {
    if (provider && Object.prototype.hasOwnProperty.call(AI_NAME_POOLS, provider)) {
      return provider;
    }
    return "generic";
  }

  function getNamePool(provider) {
    return AI_NAME_POOLS[_resolvePoolKey(provider)].slice();
  }

  // Case-insensitive trim-equal comparator used everywhere we test for
  // "same display name". Mirrors the operator's interpretation of
  // identity (whitespace + case shouldn't make two names distinct).
  function _normaliseName(name) {
    return String(name || "").trim().toLowerCase();
  }

  // Apply a numeric collision suffix to `name` such that the result
  // does not match any entry in `existingNames`. Returns the original
  // name unchanged when there's no collision; otherwise appends a
  // suffix starting at 2 (Claudio, Claudio2, Claudio3, ...).
  //
  // Comparison is case-insensitive on the trimmed name.
  function applyCollisionSuffix(name, existingNames) {
    const base = String(name || "").trim();
    if (!base) return base;
    const taken = new Set((existingNames || []).map(_normaliseName));
    if (!taken.has(_normaliseName(base))) return base;
    let suffix = 2;
    while (taken.has(_normaliseName(base + String(suffix)))) {
      suffix += 1;
      // Safety bound: don't loop forever on pathological input.
      if (suffix > 9999) return base + String(suffix);
    }
    return base + String(suffix);
  }

  // Pick a default display name for the given provider.
  //
  //   provider          — provider key (anthropic/openai/gemini/...)
  //   existingNames     — list of currently-used display names in the
  //                       session (active + pending). Used for collision
  //                       suffix.
  //   recentlyUsedNames — list of names recently suggested for this
  //                       provider on this operator's machine. Excluded
  //                       from suggestions when other pool entries are
  //                       still available.
  //
  // Returns a string. When all pool entries appear in
  // `recentlyUsedNames`, falls back to picking from the full pool (so
  // the suggestion is never empty); collision suffix still applies.
  function pickDefaultName(provider, existingNames, recentlyUsedNames) {
    const pool = getNamePool(provider);
    const recent = new Set((recentlyUsedNames || []).map(_normaliseName));
    let candidates = pool.filter((n) => !recent.has(_normaliseName(n)));
    if (candidates.length === 0) {
      // Every pool entry has been used recently — fall back to the
      // full pool so the suggestion is never empty.
      candidates = pool;
    }
    // Deterministic-ish pick: rotate through the candidates by one
    // every call. We do not need cryptographic randomness here — the
    // goal is variety for a single operator across sessions, not
    // unpredictability. Math.random() is acceptable.
    const pick = candidates[Math.floor(Math.random() * candidates.length)];
    return applyCollisionSuffix(pick, existingNames);
  }

  // Read the recently-used names for a provider from localStorage.
  // Returns an empty array on any read failure (private browsing,
  // disabled storage, JSON parse error). Browser-only — Node tests
  // pass an explicit list and don't call this.
  function loadRecentNames(provider) {
    if (typeof localStorage === "undefined") return [];
    try {
      const raw = localStorage.getItem(recentNamesStorageKey(provider));
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((s) => typeof s === "string");
    } catch (_e) {
      return [];
    }
  }

  // Append `name` to the recently-used list for `provider` with FIFO
  // eviction at RECENT_NAMES_CAP entries. No-op when the name is empty
  // OR when the operator typed a custom name not in the pool (the
  // "recently used" tracking exists to vary among pool entries; custom
  // names don't enter the suggestion path so they shouldn't displace
  // pool entries from the recency list either).
  //
  // Returns the new list (so callers can verify behaviour in tests).
  // Caller passes the existing list (loadRecentNames result) so this
  // function stays pure and testable; the localStorage write is
  // optional and skipped when localStorage is unavailable.
  function saveRecentName(provider, name, existingList) {
    const trimmed = String(name || "").trim();
    if (!trimmed) return existingList || [];
    const pool = getNamePool(provider);
    // Strip any trailing collision suffix before checking pool
    // membership: "Claudio2" should track "Claudio".
    const stripped = _stripCollisionSuffix(trimmed);
    if (!pool.some((n) => _normaliseName(n) === _normaliseName(stripped))) {
      return existingList || [];
    }
    const list = (existingList || []).filter((n) => _normaliseName(n) !== _normaliseName(stripped));
    list.push(stripped);
    while (list.length > RECENT_NAMES_CAP) {
      list.shift();
    }
    if (typeof localStorage !== "undefined") {
      try {
        localStorage.setItem(recentNamesStorageKey(provider), JSON.stringify(list));
      } catch (_e) {
        // Storage write failure is non-fatal — the list is returned to
        // the caller regardless so test paths still observe the result.
      }
    }
    return list;
  }

  // Strip a numeric collision suffix from a name. "Claudio2" → "Claudio";
  // "Claudio" → "Claudio". Single-digit-or-greater run of digits at the
  // end of the string; whitespace is trimmed first.
  function _stripCollisionSuffix(name) {
    const trimmed = String(name || "").trim();
    return trimmed.replace(/\d+$/, "");
  }

  return {
    AI_NAME_POOLS,
    RECENT_NAMES_CAP,
    recentNamesStorageKey,
    getNamePool,
    applyCollisionSuffix,
    pickDefaultName,
    loadRecentNames,
    saveRecentName,
    // Exposed for tests; the underscore prefix marks them
    // implementation-detail in the SPA path.
    _normaliseName,
    _stripCollisionSuffix,
    _resolvePoolKey,
  };
});
