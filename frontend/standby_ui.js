/* SACP Web UI - participant standby + wait_mode badge helpers.
 *
 * Spec 027 FR-052..FR-058 (spec 011 amendments). Pure-logic helpers
 * exported as UMD so the same file runs unchanged in the browser
 * (attaches to window.StandbyUI) and in Node (CommonJS) for tests.
 *
 * The React renderer in frontend/app.jsx imports these helpers via the
 * window global. Tests run them directly through require('./standby_ui').
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.StandbyUI = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {

  // FR-052: render the wait_mode badge for an AI participant.
  // Returns null for humans or for missing/empty wait_mode.
  function formatWaitModeBadge(participant) {
    if (!participant || participant.provider === "human") return null;
    var mode = participant.wait_mode || "wait_for_human";
    if (mode !== "wait_for_human" && mode !== "always") return null;
    return mode === "wait_for_human"
      ? "Wait mode: wait for human"
      : "Wait mode: always";
  }

  // FR-053: render the standby pill copy given participant + last standby event.
  // Returns null when the participant is not in standby.
  function formatStandbyPill(participant, lastEvent) {
    if (!participant || participant.status !== "standby") return null;
    var reason = lastEvent && lastEvent.reason ? lastEvent.reason : "awaiting_human";
    var copy = {
      awaiting_human: "Standby — awaiting human",
      awaiting_gate: "Standby — awaiting review gate",
      awaiting_vote: "Standby — awaiting vote",
      filler_stuck: "Standby — filler heuristic tripped",
    };
    return copy[reason] || "Standby";
  }

  // FR-056: long-term-observer detection.
  function isLongTermObserver(participant) {
    if (!participant) return false;
    var meta = participant.wait_mode_metadata || {};
    return meta.long_term_observer === true;
  }

  // FR-056: long-term-observer badge copy.
  function formatLongTermObserverBadge(participant) {
    return isLongTermObserver(participant)
      ? "Long-term observer — human absent"
      : null;
  }

  // FR-055: pivot-message styling discriminator.
  function isPivotMessage(message) {
    if (!message || !message.metadata) return false;
    return message.metadata.kind === "orchestrator_pivot";
  }

  return {
    formatWaitModeBadge: formatWaitModeBadge,
    formatStandbyPill: formatStandbyPill,
    isLongTermObserver: isLongTermObserver,
    formatLongTermObserverBadge: formatLongTermObserverBadge,
    isPivotMessage: isPivotMessage,
  };
});
