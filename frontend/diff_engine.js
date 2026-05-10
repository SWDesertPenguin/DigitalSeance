/* SACP Web UI - audit-log diff engine (spec 029 FR-008 / US2).
 *
 * Pure-logic wrapper around jsdiff that enforces the size-threshold
 * dispatch defined in shared-module-contracts.md §3 / §4:
 *   <= 50,000 chars -> main-thread sync diff
 *   50,001..500,000 -> Web Worker (inline-blob) with main-thread fallback
 *   > 500,000       -> raw display, no diff computation
 *
 * The threshold constants are LOCKED per the contract; no per-call
 * override and no env-var tuning. Spec 024 FR-014 inherits these
 * constants by importing this module rather than redefining them.
 *
 * In the browser, the host page loads jsdiff via the CDN <script> in
 * index.html which sets ``window.Diff``. In Node tests, the consumer
 * may inject its own ``Diff`` shim via the exported ``setDiffLibrary``
 * helper so the tests do not have to declare a third-party dependency.
 *
 * UMD-style export so the same file runs unchanged in the browser
 * (attaches to window.DiffEngine) AND in Node (CommonJS) for tests.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DiffEngine = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Locked constants per shared-module-contracts.md §3 / §4. Do NOT
  // expose a runtime override; threshold changes require a coordinated
  // amendment across the contract document, this module, spec 029
  // FR-008, and spec 024 FR-014.
  const MAIN_THREAD_BYTE_THRESHOLD = 50000;
  const WORKER_BYTE_THRESHOLD = 500000;

  // Lazily resolved jsdiff handle. In the browser this is window.Diff
  // after index.html's <script> tag executes. In Node tests, the test
  // file calls setDiffLibrary() with a stub that exposes diffLines /
  // diffWords / diffJson. _resolveDiff() throws a clear error when no
  // library is attached so the failure mode is obvious in CI logs.
  let _diffLib = null;

  function setDiffLibrary(lib) {
    _diffLib = lib;
  }

  function _resolveDiff() {
    if (_diffLib) return _diffLib;
    if (typeof globalThis !== "undefined" && globalThis.Diff) {
      _diffLib = globalThis.Diff;
      return _diffLib;
    }
    throw new Error(
      "DiffEngine: jsdiff library not loaded; expected globalThis.Diff" +
        " (browser) or setDiffLibrary(stub) (Node tests).",
    );
  }

  // Char count of the larger of the two values; null/undefined treated
  // as zero. Matches the threshold contract: the dispatch decision is
  // driven by the largest value the renderer would have to walk.
  function _maxByteSize(previousValue, newValue) {
    const a = previousValue == null ? 0 : String(previousValue).length;
    const b = newValue == null ? 0 : String(newValue).length;
    return a > b ? a : b;
  }

  // Returns "main" | "worker" | "raw" per the locked thresholds.
  // Pure function; safe to call before the jsdiff library has loaded.
  function chooseDiffMode(byteSize) {
    if (byteSize <= MAIN_THREAD_BYTE_THRESHOLD) return "main";
    if (byteSize <= WORKER_BYTE_THRESHOLD) return "worker";
    return "raw";
  }

  // Synchronous line-by-line diff. ``format`` is "json" | "text" |
  // "auto"; "auto" probes JSON.parse on both sides and uses diffJson
  // when both succeed, else diffLines on the raw strings. Returns the
  // jsdiff change-array shape: [{ added, removed, value, count }, ...]
  function diffLinesSync(previousValue, newValue, format) {
    const lib = _resolveDiff();
    const prev = previousValue == null ? "" : String(previousValue);
    const next = newValue == null ? "" : String(newValue);
    const mode = format || "auto";
    if (mode === "json") {
      return lib.diffJson(_safeJsonParse(prev), _safeJsonParse(next));
    }
    if (mode === "auto") {
      const prevJson = _tryJsonParse(prev);
      const nextJson = _tryJsonParse(next);
      if (prevJson.ok && nextJson.ok) {
        return lib.diffJson(prevJson.value, nextJson.value);
      }
    }
    return lib.diffLines(prev, next);
  }

  // Synchronous word-level diff for the per-row toggle. Always operates
  // on the raw strings (word-level over a JSON dump is rarely useful
  // and the toggle is a manual user opt-in).
  function diffWordsSync(previousValue, newValue) {
    const lib = _resolveDiff();
    const prev = previousValue == null ? "" : String(previousValue);
    const next = newValue == null ? "" : String(newValue);
    return lib.diffWords(prev, next);
  }

  // Async Worker bootstrap for the 50KB-500KB tier. When Worker / Blob
  // are unavailable (legacy runtimes, restrictive CSP), falls back to
  // a chunked main-thread render via _yieldingDiffLines so the budget
  // contract still holds without a hard-failed Worker requirement.
  function diffLinesViaWorker(previousValue, newValue, format) {
    if (typeof Worker === "undefined" || typeof Blob === "undefined") {
      return _yieldingDiffLines(previousValue, newValue, format);
    }
    return new Promise((resolve, reject) => {
      let worker;
      try {
        // The worker pulls jsdiff from the same CDN URL the host page
        // uses, so the inline-blob script stays small. importScripts
        // is synchronous inside a worker so the message handler can
        // trust globalThis.Diff is present once it fires.
        const diffSrc = (
          typeof globalThis !== "undefined" && globalThis.SACP_DIFF_SRC
        ) || "https://cdn.jsdelivr.net/npm/diff@5.2.0/dist/diff.min.js";
        const workerSrc =
          "importScripts(" + JSON.stringify(diffSrc) + ");\n" +
          "self.onmessage = function (e) {\n" +
          "  var d = e.data || {};\n" +
          "  var prev = d.prev == null ? '' : String(d.prev);\n" +
          "  var next = d.next == null ? '' : String(d.next);\n" +
          "  var fmt = d.format || 'auto';\n" +
          "  var result;\n" +
          "  try {\n" +
          "    if (fmt === 'json') {\n" +
          "      result = self.Diff.diffJson(JSON.parse(prev), JSON.parse(next));\n" +
          "    } else { result = self.Diff.diffLines(prev, next); }\n" +
          "    self.postMessage({ ok: true, changes: result });\n" +
          "  } catch (err) {\n" +
          "    self.postMessage({ ok: false, error: String(err && err.message || err) });\n" +
          "  }\n" +
          "};\n";
        const blob = new Blob([workerSrc], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        worker = new Worker(url);
        worker.onmessage = function (e) {
          worker.terminate();
          URL.revokeObjectURL(url);
          if (e.data && e.data.ok) {
            resolve(e.data.changes);
          } else {
            reject(new Error(e.data && e.data.error || "diff worker failed"));
          }
        };
        worker.onerror = function (err) {
          worker.terminate();
          URL.revokeObjectURL(url);
          reject(err);
        };
        worker.postMessage({
          prev: previousValue,
          next: newValue,
          format: format || "auto",
        });
      } catch (e) {
        if (worker) {
          try { worker.terminate(); } catch (_) { /* ignore */ }
        }
        // Fall back to the chunked main-thread render rather than
        // bubbling the Worker construction failure up to the caller.
        _yieldingDiffLines(previousValue, newValue, format).then(resolve, reject);
      }
    });
  }

  // Fallback for the 50KB-500KB tier when no Worker is available.
  // Computes the diff on the main thread but yields once via setTimeout
  // so the caller's render loop can show a "computing diff" placeholder
  // before the synchronous walk consumes the budget. Matches the
  // research.md §3 design for legacy / restricted-CSP environments.
  function _yieldingDiffLines(previousValue, newValue, format) {
    return new Promise((resolve, reject) => {
      const tick = (typeof setTimeout === "function") ? setTimeout : function (fn) { fn(); };
      tick(function () {
        try {
          resolve(diffLinesSync(previousValue, newValue, format));
        } catch (e) {
          reject(e);
        }
      }, 0);
    });
  }

  // Helpers: tolerant JSON parse for the "auto" format probe + a
  // strict variant for explicit "json" mode (caller already promised
  // the values parse).
  function _tryJsonParse(s) {
    try { return { ok: true, value: JSON.parse(s) }; }
    catch (_e) { return { ok: false, value: null }; }
  }

  function _safeJsonParse(s) {
    try { return JSON.parse(s); }
    catch (_e) { return s; }
  }

  return {
    MAIN_THREAD_BYTE_THRESHOLD: MAIN_THREAD_BYTE_THRESHOLD,
    WORKER_BYTE_THRESHOLD: WORKER_BYTE_THRESHOLD,
    chooseDiffMode: chooseDiffMode,
    diffLinesSync: diffLinesSync,
    diffWordsSync: diffWordsSync,
    diffLinesViaWorker: diffLinesViaWorker,
    setDiffLibrary: setDiffLibrary,
    // Internal helper exposed for the maxByteSize tests; the renderer
    // also uses it to pick chooseDiffMode's input without re-deriving.
    _maxByteSize: _maxByteSize,
  };
});
