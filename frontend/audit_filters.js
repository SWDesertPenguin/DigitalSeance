/* SACP Web UI - audit-log filter logic (spec 029 FR-012 / FR-013 / US3).
 *
 * Pure-logic helpers for the AuditLogPanel's three-axis filter UI:
 * actor, action-type, time-range. Filters apply client-side to the
 * already-loaded page (FR-012 v1 limitation - server-side filtering
 * is intentionally out of scope for the first cut). The badge counter
 * machinery (FR-013) lives in the React component; this module owns
 * the matching predicate so the count and the filtered view share one
 * truth.
 *
 * The "actor" axis matches against ``row.actor_id``. The orchestrator
 * sentinel actor is the empty/null actor_id case; the UI surfaces it
 * as a special filter option keyed ``"__orchestrator__"`` and we map
 * that back to "row has no actor_id" in matchesFilters.
 *
 * The "action-type" axis matches against ``row.action`` (the raw
 * registry key, NOT the human label - operators filter by behaviour,
 * not by the prose).
 *
 * The "time-range" axis is a preset relative window expressed as a
 * { kind: "preset", preset: "1h" | "24h" | "7d" | "all" } criterion;
 * "all" disables the axis. Custom date pickers are deferred to a
 * future iteration per tasks.md; preset windows cover the operational
 * use cases without shipping a date-picker component on the CDN-loaded
 * SPA.
 *
 * UMD-style export so the same file runs unchanged in the browser
 * (attaches to window.AuditFilters) AND in Node (CommonJS) for tests.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.AuditFilters = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Sentinel actor key for the "Orchestrator" filter option. The
  // backend stores orchestrator-actor rows with actor_id=null and
  // returns actor_display_name="Orchestrator"; we use this string in
  // the filter dropdown so the React layer doesn't have to special-case
  // null vs uuid for the filter <select>.
  const ORCHESTRATOR_ACTOR_KEY = "__orchestrator__";

  // Preset relative-time windows. Order in the dropdown matches this
  // declaration order; "all" is the no-op default. Seconds chosen to
  // match the conventional "last N" semantics operators expect.
  const TIME_PRESETS = [
    { key: "all", label: "All time", seconds: null },
    { key: "1h",  label: "Last hour",   seconds: 60 * 60 },
    { key: "24h", label: "Last 24h",    seconds: 60 * 60 * 24 },
    { key: "7d",  label: "Last 7 days", seconds: 60 * 60 * 24 * 7 },
  ];

  // Empty filter shape - the React layer initializes useState with
  // this, and "Clear filters" resets to it. Keeping the shape exported
  // means the test harness and the component agree on the contract.
  const EMPTY_FILTERS = Object.freeze({
    actor: null,        // null = any; ORCHESTRATOR_ACTOR_KEY or actor_id uuid
    action: null,       // null = any; raw registry key string
    timePreset: "all",  // "all" | "1h" | "24h" | "7d"
  });

  // Coerce a row.timestamp value into epoch ms for the time-range
  // comparison. Accepts ISO-8601 strings (the FR-001 endpoint shape),
  // Date objects (defensive), and finite numbers (epoch ms). Returns
  // null on anything we cannot parse so the time filter degrades to
  // "include the row" rather than throwing in the render path.
  function _rowTimeMs(row) {
    if (!row) return null;
    const ts = row.timestamp;
    if (ts == null) return null;
    if (ts instanceof Date) {
      const ms = ts.getTime();
      return Number.isFinite(ms) ? ms : null;
    }
    if (typeof ts === "number" && Number.isFinite(ts)) {
      return ts;
    }
    if (typeof ts === "string" && ts.length > 0) {
      const ms = Date.parse(ts);
      return Number.isFinite(ms) ? ms : null;
    }
    return null;
  }

  // Look up a preset by key. Defaults to "all" on unknown input so a
  // stale persisted value (or a UI bug) cannot accidentally hide every
  // row. Operators explicitly opt into narrowing.
  function _resolvePreset(key) {
    for (const preset of TIME_PRESETS) {
      if (preset.key === key) return preset;
    }
    return TIME_PRESETS[0];
  }

  // True when ``row`` satisfies every active axis in ``filters``. An
  // axis with a null/empty/all value is inactive and matches any row.
  // The optional ``nowMs`` parameter exists so tests can pin the clock;
  // production callers omit it and we default to Date.now().
  function matchesFilters(row, filters, nowMs) {
    if (!row) return false;
    const f = filters || EMPTY_FILTERS;

    if (f.actor) {
      if (f.actor === ORCHESTRATOR_ACTOR_KEY) {
        // Orchestrator-actor rows have null/empty actor_id per the
        // FR-001 endpoint contract.
        if (row.actor_id != null && row.actor_id !== "") return false;
      } else if (row.actor_id !== f.actor) {
        return false;
      }
    }

    if (f.action && row.action !== f.action) {
      return false;
    }

    if (f.timePreset && f.timePreset !== "all") {
      const preset = _resolvePreset(f.timePreset);
      if (preset.seconds != null) {
        const rowMs = _rowTimeMs(row);
        if (rowMs == null) return false;
        const now = typeof nowMs === "number" ? nowMs : Date.now();
        const cutoff = now - preset.seconds * 1000;
        if (rowMs < cutoff) return false;
      }
    }

    return true;
  }

  // Filter ``rows`` to the subset that satisfies ``filters``. Pure
  // function, returns a new array; never mutates the input. Empty /
  // unset filters return the input unchanged (same shape, new array).
  function applyFilters(rows, filters, nowMs) {
    if (!Array.isArray(rows)) return [];
    if (!filters || isEmpty(filters)) return rows.slice();
    return rows.filter((r) => matchesFilters(r, filters, nowMs));
  }

  // True when ``filters`` would include every row - used by callers
  // that want to short-circuit the badge counter (no axis active means
  // nothing can ever be "hidden").
  function isEmpty(filters) {
    if (!filters) return true;
    if (filters.actor) return false;
    if (filters.action) return false;
    if (filters.timePreset && filters.timePreset !== "all") return false;
    return true;
  }

  return {
    ORCHESTRATOR_ACTOR_KEY,
    TIME_PRESETS,
    EMPTY_FILTERS,
    matchesFilters,
    applyFilters,
    isEmpty,
  };
});
