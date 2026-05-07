/* SACP Web UI — small text helpers.
 *
 * Pure-logic module loaded ahead of app.jsx. UMD-style export so the
 * same file runs unchanged in the browser (attaches to window) AND in
 * Node (CommonJS module.exports) for tests.
 *
 * Currently houses the filename slugifier used by export UX and any
 * future surface that needs the session-name → safe-filename
 * conversion. Keeps the helper testable in Node without pulling JSX
 * into the test path.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Lower-case, replace any run of whitespace OR non-alphanumeric
  // characters with a single hyphen, collapse repeated hyphens (the
  // replace already collapses runs of *one class* but not mixed
  // whitespace+punctuation runs), trim hyphens from both ends.
  // Returns the empty string on null / undefined / empty input — the
  // caller decides the fallback.
  //
  // Examples:
  //   slugify("Brave Wolf c667")       → "brave-wolf-c667"
  //   slugify("  research / co-author") → "research-co-author"
  //   slugify("ünicode!ish ✓")          → "nicode-ish" (non-ASCII gone)
  //   slugify("")                       → ""
  //   slugify(null)                     → ""
  function slugify(input) {
    if (input == null) return "";
    const s = String(input);
    // Lowercase, replace anything not [a-z0-9] with a hyphen.
    const replaced = s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    // Trim leading + trailing hyphens.
    const trimmed = replaced.replace(/^-+|-+$/g, "");
    return trimmed;
  }

  // Build a filename for a transcript / data export.
  //
  //   sessionName  — raw session name (may be null / empty)
  //   format       — "markdown" | "json" (the SPA's existing pair).
  //                  Anything else is treated as the format itself
  //                  (the extension is the format string).
  //   fallback     — generic filename used when the session name is
  //                  empty / unset (prevents the "" filename bug).
  //
  // Returns the filename string with an explicit extension. Operators
  // who name their session "Brave Wolf c667" get
  // "brave-wolf-c667.md" instead of the previous
  // "sacp-<uuid>-<timestamp>.md" generic.
  function buildExportFilename(sessionName, format, fallback) {
    const ext = format === "json" ? "json" : (format === "markdown" ? "md" : String(format || "txt"));
    const slug = slugify(sessionName);
    if (slug) return slug + "." + ext;
    if (fallback) {
      // If the caller provided a fallback, append the extension only
      // if it's not already there. The existing generic shape carries
      // the extension already (e.g. "sacp-<uuid>-<ts>.md").
      if (fallback.toLowerCase().endsWith("." + ext.toLowerCase())) return fallback;
      return fallback + "." + ext;
    }
    return "export." + ext;
  }

  return {
    slugify,
    buildExportFilename,
  };
});
