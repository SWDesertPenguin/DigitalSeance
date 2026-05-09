/* SACP Web UI - audit-log action-label registry mirror.
 *
 * Frontend mirror of src/orchestrator/audit_labels.py per spec 029 FR-006
 * and shared-module-contracts.md §1. Loaded ahead of app.jsx via <script>
 * in index.html; consumed by the AuditLogPanel and the audit_log_appended
 * WS handler for consistent action-label rendering.
 *
 * The CI parity gate (scripts/check_audit_label_parity.py) fails the
 * build if backend and frontend disagree on keys or label strings.
 * scrub_value is backend-only; the frontend mirror omits the field
 * because the SPA never sees raw values for scrub_value=true actions
 * (server replaces them with "[scrubbed]" before transmission).
 *
 * UMD-style export so the same file runs unchanged in the browser
 * (attaches to window.AuditLabels) AND in Node (CommonJS) for tests.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.AuditLabels = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Mirrors src/orchestrator/audit_labels.LABELS (label strings only).
  // Keep keys + label strings byte-identical to the Python registry; the
  // CI parity gate enforces equality.
  const LABELS = {
    "add_participant": { label: "Facilitator added participant" },
    "approve_participant": { label: "Facilitator approved participant" },
    "reject_participant": { label: "Facilitator rejected participant" },
    "remove_participant": { label: "Facilitator removed participant" },
    "pause_loop": { label: "Facilitator paused the loop" },
    "resume_loop": { label: "Facilitator resumed the loop" },
    "start_loop": { label: "Facilitator started the loop" },
    "stop_loop": { label: "Facilitator stopped the loop" },
    "transfer_facilitator": { label: "Facilitator role transferred" },
    "set_routing_preference": { label: "Routing preference changed" },
    "set_budget": { label: "Budget changed" },
    "review_gate_approve": { label: "Review gate: draft approved" },
    "review_gate_reject": { label: "Review gate: draft rejected" },
    "review_gate_edit": { label: "Review gate: draft edited" },
    "review_gate_pause_scope_changed": { label: "Review-gate pause scope changed" },
    "rotate_token": { label: "Auth token rotated" },
    "revoke_token": { label: "Auth token revoked" },
    "cap_set": { label: "Session length cap changed" },
    "auto_pause_on_cap": { label: "Loop auto-paused (length cap reached)" },
    "manual_stop_during_conclude": { label: "Loop manually stopped during conclude phase" },
    "session_config_change": { label: "Session config changed" },
  };

  // Return the registered label for `action`, or the
  // "[unregistered: <action>]" fallback per spec FR-015. Does not log -
  // the SPA may render thousands of rows on a long session and a
  // console.warn per row would spam at panel-load volume.
  function formatLabel(action) {
    const entry = LABELS[action];
    if (!entry) {
      return "[unregistered: " + String(action) + "]";
    }
    return String(entry.label);
  }

  return { LABELS, formatLabel };
});
