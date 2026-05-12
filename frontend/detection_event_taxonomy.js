/* SACP Web UI - detection-event taxonomy registry mirror (spec 022).
 *
 * Frontend mirror of src/web_ui/detection_events.py::EVENT_CLASSES per
 * spec 022 data-model.md "Class-mapping registry" and research.md §5.
 * Loaded ahead of app.jsx via <script> in index.html; consumed by the
 * DetectionHistoryPanel React component and the detection_event_appended
 * WS handler for consistent class-label rendering.
 *
 * The CI parity gate (scripts/check_detection_taxonomy_parity.py) fails
 * the build if backend and frontend disagree on keys or label strings.
 *
 * UMD-style export so the same file runs unchanged in the browser
 * (attaches to window.DetectionEventTaxonomy) AND in Node (CommonJS)
 * for tests.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DetectionEventTaxonomy = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Mirrors src/web_ui/detection_events.EVENT_CLASSES (label strings only).
  // Keep keys + label strings byte-identical to the Python registry; the
  // CI parity gate enforces equality.
  const EVENT_CLASSES = {
    "ai_question_opened": { label: "AI question opened" },
    "ai_exit_requested": { label: "AI exit requested" },
    "density_anomaly": { label: "Density anomaly" },
    "mode_recommendation": { label: "Mode recommendation" },
    "mode_change": { label: "Mode change" },
  };

  // Return the registered label for `classKey`, or the
  // "[unregistered: <key>]" fallback. Mirrors AuditLabels.formatLabel:
  // does not log, because the panel may render hundreds of rows on a long
  // session and a console.warn per row would spam at load volume.
  function formatClassLabel(classKey) {
    const entry = EVENT_CLASSES[classKey];
    if (!entry) {
      return "[unregistered: " + String(classKey) + "]";
    }
    return entry.label;
  }

  return { EVENT_CLASSES: EVENT_CLASSES, formatClassLabel: formatClassLabel };
});
