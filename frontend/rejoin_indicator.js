/* SACP Web UI — participant re-join identity indicator.
 *
 * Pure-logic module loaded ahead of app.jsx. UMD-style export so the
 * same file runs unchanged in the browser (attaches to window) AND in
 * Node (CommonJS module.exports) for tests.
 *
 * Detection scope is the CURRENT SESSION ONLY: we look at the
 * participants list passed in by the SPA, which is already filtered
 * server-side to one session. A coincidental same-name participant in
 * a different session is not visible here and therefore cannot trigger
 * the re-joined pill.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Default window for the "Re-joined" pill (in turns after join).
  // Exposed so the SPA can use the same constant when constructing
  // tooltip text and gating the pill.
  const REJOIN_PILL_WINDOW_TURNS = 10;

  // Participant statuses that count as "departed" for re-join
  // detection. Mirrors the existing isDeparted gate in
  // ParticipantCard so the two surfaces agree on what counts.
  const DEPARTED_STATUSES = new Set(["offline", "removed", "reset"]);

  // Participant statuses that count as "active" for re-join
  // detection. These are the participants who CAN be flagged as
  // re-joined when a prior departed participant has the same name.
  const ACTIVE_STATUSES = new Set(["active", "approved"]);

  function _normaliseName(name) {
    return String(name || "").trim().toLowerCase();
  }

  function _isDeparted(participant) {
    return Boolean(participant) && DEPARTED_STATUSES.has(participant.status);
  }

  function _isActive(participant) {
    return Boolean(participant) && ACTIVE_STATUSES.has(participant.status);
  }

  // Last-N characters of a participant id, lowercased for visual
  // consistency with hex-style hash fragments. Returns the empty
  // string when the input is missing; never throws.
  function shortIdBadge(participantId, length) {
    const id = String(participantId || "");
    if (!id) return "";
    const n = typeof length === "number" && length > 0 ? length : 4;
    return id.slice(-n).toLowerCase();
  }

  // Find a prior departed participant in the same session with a
  // matching display_name. "Prior" here means "currently in
  // departed status" — the data model doesn't carry departure
  // ordering metadata, but a session's participant list is the
  // authoritative current state, so any departed entry with a
  // matching name was necessarily prior to the active one.
  //
  // Comparison is case-insensitive and trim-aware. Returns the
  // departed participant object, or null if none.
  function findPriorRemovedSameName(activeParticipant, allParticipants) {
    if (!_isActive(activeParticipant)) return null;
    const target = _normaliseName(activeParticipant.display_name);
    if (!target) return null;
    const list = Array.isArray(allParticipants) ? allParticipants : [];
    for (const p of list) {
      if (!p || p.id === activeParticipant.id) continue;
      if (!_isDeparted(p)) continue;
      if (_normaliseName(p.display_name) === target) return p;
    }
    return null;
  }

  // Decide whether the "Re-joined" pill should render for the given
  // active participant.
  //
  //   participant       — the active participant being rendered
  //   allParticipants   — full participants list for the session
  //   currentTurn       — session's current turn counter
  //   lifecycle         — { [participant_id]: {joined_at_turn, ...} }
  //   windowTurns       — pill window (turns after join). Defaults to
  //                       REJOIN_PILL_WINDOW_TURNS.
  //
  // Returns true when:
  //   - participant is in an active status AND
  //   - some other participant in the list is in departed status with
  //     the same display_name (case-insensitive, trimmed) AND
  //   - lifecycle records the participant was first observed within
  //     `windowTurns` of currentTurn.
  //
  // Returns false otherwise. Pre-existing participants from
  // state_snapshot (lifecycle.first_observed_turn unset or null) do
  // NOT trigger the pill — we only flag participants we observed
  // joining live.
  function shouldShowRejoinedPill(participant, allParticipants, currentTurn, lifecycle, windowTurns) {
    if (!_isActive(participant)) return false;
    const prior = findPriorRemovedSameName(participant, allParticipants);
    if (!prior) return false;
    const lc = (lifecycle || {})[participant.id];
    if (!lc || lc.first_observed_turn == null) return false;
    const window = typeof windowTurns === "number" && windowTurns > 0
      ? windowTurns
      : REJOIN_PILL_WINDOW_TURNS;
    const turn = typeof currentTurn === "number" ? currentTurn : 0;
    return (turn - lc.first_observed_turn) < window;
  }

  // Build the tooltip text for a participant's display_name. Includes
  // the full participant_id, the join timestamp (locale-formatted),
  // and the prior same-name removal timestamp when one is detectable.
  //
  // Locale formatting uses Intl.DateTimeFormat when available; in Node
  // tests the formatter falls back to ISO. Pure function — no DOM
  // access, no side effects.
  function buildIdentityTooltip(participant, allParticipants, lifecycle, locale) {
    if (!participant) return "";
    const lines = [];
    lines.push("ID: " + String(participant.id || ""));
    const lc = (lifecycle || {})[participant.id] || {};
    if (lc.first_observed_iso) {
      lines.push("Joined: " + _formatLocaleTime(lc.first_observed_iso, locale));
    }
    const prior = findPriorRemovedSameName(participant, allParticipants);
    if (prior) {
      const priorLc = (lifecycle || {})[prior.id] || {};
      if (priorLc.removed_at_iso) {
        lines.push("Prior same-name removed: " + _formatLocaleTime(priorLc.removed_at_iso, locale));
      } else {
        lines.push("Prior same-name removed: (time unavailable)");
      }
    }
    return lines.join("\n");
  }

  function _formatLocaleTime(iso, locale) {
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      if (typeof Intl !== "undefined" && Intl.DateTimeFormat) {
        const fmt = new Intl.DateTimeFormat(locale || undefined, {
          dateStyle: "medium",
          timeStyle: "medium",
        });
        return fmt.format(d);
      }
      return d.toISOString();
    } catch (_e) {
      return iso;
    }
  }

  // Update a lifecycle map given an incoming participant_update event.
  // Pure function: caller owns merging the result into reducer state.
  //
  //   prevLifecycle  — current map { [id]: lifecycle entry }
  //   prevParticipants — current participants list (to detect "new")
  //   updated        — the new participant payload from the event
  //   currentTurn    — session's current turn at update time
  //   nowIso         — ISO timestamp string at update time
  //
  // Behaviour:
  //   - First time we see this id: set first_observed_turn / iso.
  //   - Status transitions into a departed value: set removed_at_*.
  //   - Status transitions out of departed back to active: clear
  //     removed_at_* and refresh first_observed_* so a re-add is
  //     treated as a new join window.
  function applyLifecycleOnUpdate(prevLifecycle, prevParticipants, updated, currentTurn, nowIso) {
    const map = { ...(prevLifecycle || {}) };
    if (!updated || !updated.id) return map;
    const prev = (Array.isArray(prevParticipants) ? prevParticipants : [])
      .find((p) => p && p.id === updated.id) || null;
    const entry = map[updated.id] ? { ...map[updated.id] } : {};
    const prevDeparted = _isDeparted(prev);
    const newlyDeparted = _isDeparted(updated);
    const newActive = _isActive(updated);
    if (!prev) {
      // First time we see this id — capture the join window.
      entry.first_observed_turn = currentTurn ?? 0;
      entry.first_observed_iso = nowIso;
    } else if (prevDeparted && newActive) {
      // Re-add of an id we previously saw depart. Reset the join
      // window so the pill applies for the new join.
      entry.first_observed_turn = currentTurn ?? 0;
      entry.first_observed_iso = nowIso;
      entry.removed_at_turn = null;
      entry.removed_at_iso = null;
    }
    if (!prevDeparted && newlyDeparted) {
      entry.removed_at_turn = currentTurn ?? 0;
      entry.removed_at_iso = nowIso;
    }
    map[updated.id] = entry;
    return map;
  }

  // Update a lifecycle map for a hard-removed participant. Behaves
  // like a transition into departed status from the lifecycle's
  // perspective (captures removal time).
  function applyLifecycleOnRemove(prevLifecycle, removedId, currentTurn, nowIso) {
    const map = { ...(prevLifecycle || {}) };
    if (!removedId) return map;
    const entry = map[removedId] ? { ...map[removedId] } : {};
    entry.removed_at_turn = currentTurn ?? 0;
    entry.removed_at_iso = nowIso;
    map[removedId] = entry;
    return map;
  }

  // Seed lifecycle entries from a state_snapshot (initial connect or
  // reconnect). For pre-existing participants we set
  // first_observed_turn=null deliberately — the SPA hasn't observed
  // them joining live, so the pill MUST NOT fire for them. Departed
  // entries get their removed_at_iso seeded to the snapshot time so
  // the tooltip's "prior same-name removed" line has SOMETHING to
  // show, marked as approximate.
  function seedLifecycleFromSnapshot(participants, nowIso) {
    const map = {};
    const list = Array.isArray(participants) ? participants : [];
    for (const p of list) {
      if (!p || !p.id) continue;
      const entry = { first_observed_turn: null, first_observed_iso: null };
      if (_isDeparted(p)) {
        entry.removed_at_turn = null;
        entry.removed_at_iso = nowIso;
        entry.removed_iso_is_approximate = true;
      }
      map[p.id] = entry;
    }
    return map;
  }

  return {
    REJOIN_PILL_WINDOW_TURNS,
    DEPARTED_STATUSES,
    ACTIVE_STATUSES,
    shortIdBadge,
    findPriorRemovedSameName,
    shouldShowRejoinedPill,
    buildIdentityTooltip,
    applyLifecycleOnUpdate,
    applyLifecycleOnRemove,
    seedLifecycleFromSnapshot,
    _normaliseName,
    _isDeparted,
    _isActive,
  };
});
