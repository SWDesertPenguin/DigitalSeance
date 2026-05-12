/* SACP Web UI - detection-event history pure-logic helpers (spec 022).
 *
 * Pure-logic helpers consumed by the DetectionHistoryPanel React
 * component in frontend/app.jsx per spec 011 FR-037..FR-039
 * (Session 2026-05-11 amendment). Factored out as a UMD module so
 * the filter composition, hidden-events badge computation, sort,
 * and snippet truncation logic can be exercised under Node without
 * a browser DOM (per frontend_polish_module_pattern memory).
 *
 * UMD-style export: window.DetectionHistoryFilters in browser,
 * CommonJS require() in Node.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DetectionHistoryFilters = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {

  // ---------------------------------------------------------------------
  // Default filter state per spec 011 FR-037 / spec 022 research §8
  // ---------------------------------------------------------------------

  function defaultFilters() {
    return {
      type: "all",          // one of EVENT_CLASSES keys or "all"
      participant: "all",   // one of session participant ids or "all"
      timeRange: "all",     // preset chip key or {fromIso, toIso}
      disposition: "all",   // one of disposition enum values or "all"
    };
  }

  // ---------------------------------------------------------------------
  // Per-axis predicates — each returns boolean for one event/filter pair
  // ---------------------------------------------------------------------

  function _typeMatches(filter, event) {
    if (!filter || filter === "all") return true;
    return event.event_class === filter;
  }

  function _participantMatches(filter, event) {
    if (!filter || filter === "all") return true;
    return event.participant_id === filter;
  }

  function _timeRangeMatches(filter, event) {
    if (!filter || filter === "all") return true;
    const ts = event.timestamp;
    if (!ts) return true;
    const eventMs = Date.parse(ts);
    if (Number.isNaN(eventMs)) return true;
    if (typeof filter === "string") {
      const presetMs = _presetWindowMs(filter);
      if (presetMs == null) return true;
      return Date.now() - eventMs <= presetMs;
    }
    if (filter && typeof filter === "object") {
      if (filter.fromIso && eventMs < Date.parse(filter.fromIso)) return false;
      if (filter.toIso && eventMs > Date.parse(filter.toIso)) return false;
      return true;
    }
    return true;
  }

  function _presetWindowMs(key) {
    switch (key) {
      case "5m": return 5 * 60 * 1000;
      case "15m": return 15 * 60 * 1000;
      case "1h": return 60 * 60 * 1000;
      default: return null;
    }
  }

  function _dispositionMatches(filter, event) {
    if (!filter || filter === "all") return true;
    return event.disposition === filter;
  }

  // ---------------------------------------------------------------------
  // Composition (AND-semantics across all four axes)
  // ---------------------------------------------------------------------

  function applyFilters(events, filters) {
    const f = filters || defaultFilters();
    return (events || []).filter((event) => (
      _typeMatches(f.type, event)
      && _participantMatches(f.participant, event)
      && _timeRangeMatches(f.timeRange, event)
      && _dispositionMatches(f.disposition, event)
    ));
  }

  // ---------------------------------------------------------------------
  // Hidden-events badges (per-axis exclusion count)
  // ---------------------------------------------------------------------

  function hiddenByAxis(events, filters) {
    const f = filters || defaultFilters();
    let typeHidden = 0;
    let participantHidden = 0;
    let timeRangeHidden = 0;
    let dispositionHidden = 0;
    for (const event of events || []) {
      if (!_typeMatches(f.type, event)) typeHidden += 1;
      if (!_participantMatches(f.participant, event)) participantHidden += 1;
      if (!_timeRangeMatches(f.timeRange, event)) timeRangeHidden += 1;
      if (!_dispositionMatches(f.disposition, event)) dispositionHidden += 1;
    }
    return {
      type: typeHidden,
      participant: participantHidden,
      timeRange: timeRangeHidden,
      disposition: dispositionHidden,
    };
  }

  // ---------------------------------------------------------------------
  // Sort + truncation (FR-039)
  // ---------------------------------------------------------------------

  function sortEvents(events, order) {
    const list = (events || []).slice();
    const dir = order === "asc" ? 1 : -1;
    list.sort((a, b) => {
      const aMs = Date.parse(a.timestamp || "");
      const bMs = Date.parse(b.timestamp || "");
      if (Number.isNaN(aMs) || Number.isNaN(bMs)) return 0;
      return dir * (aMs - bMs);
    });
    return list;
  }

  const TRIGGER_SNIPPET_DISPLAY_CAP = 200;

  function truncateSnippet(snippet, cap) {
    const limit = cap || TRIGGER_SNIPPET_DISPLAY_CAP;
    if (snippet == null) return { display: "", full: "", truncated: false };
    const s = String(snippet);
    if (s.length <= limit) return { display: s, full: s, truncated: false };
    return { display: s.slice(0, limit), full: s, truncated: true };
  }

  // ---------------------------------------------------------------------
  // Distinct participants helper (for FR-037 participant-filter options)
  // ---------------------------------------------------------------------

  function distinctParticipants(events) {
    const seen = new Set();
    for (const event of events || []) {
      if (event && event.participant_id) seen.add(event.participant_id);
    }
    return Array.from(seen).sort();
  }

  return {
    defaultFilters: defaultFilters,
    applyFilters: applyFilters,
    hiddenByAxis: hiddenByAxis,
    sortEvents: sortEvents,
    truncateSnippet: truncateSnippet,
    distinctParticipants: distinctParticipants,
    TRIGGER_SNIPPET_DISPLAY_CAP: TRIGGER_SNIPPET_DISPLAY_CAP,
  };
});
