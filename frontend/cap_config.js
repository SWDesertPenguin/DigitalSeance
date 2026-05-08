/* SACP Web UI — session-length cap configuration helpers.
 *
 * Pure-logic module for the cap-config control set used in the
 * session-create modal (spec 011 FR-021) and the facilitator
 * session-settings panel (spec 011 FR-022). Spec 025 §FR-023.
 *
 * UMD-style export — runs unchanged in the browser (attaches to
 * window) AND in Node (CommonJS module.exports) for tests.
 *
 * No React or DOM access in this file; all functions are pure and
 * synchronous. Wiring into app.jsx is done by the caller.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Preset cap shapes per spec 025 FR-023 and research.md §6.
  // Short / Medium / Long / Custom match the session-create modal options.
  const PRESETS = {
    short:  { kind: "both", seconds: 1800,  turns: 20  },
    medium: { kind: "both", seconds: 7200,  turns: 50  },
    long:   { kind: "both", seconds: 28800, turns: 200 },
    none:   { kind: "none", seconds: null,  turns: null },
  };

  // Preset labels suitable for a <select> element.
  const PRESET_OPTIONS = [
    { value: "short",  label: "Short  (30 min / 20 turns)"   },
    { value: "medium", label: "Medium (2 hr / 50 turns)"     },
    { value: "long",   label: "Long   (8 hr / 200 turns)"    },
    { value: "custom", label: "Custom"                        },
    { value: "none",   label: "No cap"                       },
  ];

  // Valid range boundaries per spec 025 FR-020.
  const SECONDS_MIN = 60;
  const SECONDS_MAX = 2592000;
  const TURNS_MIN   = 1;
  const TURNS_MAX   = 10000;

  // Return the canonical cap values for a built-in preset, or null for
  // 'custom' (caller handles custom via explicit field values).
  function getPresetValues(preset) {
    const key = (preset || "none").toLowerCase();
    return PRESETS[key] || null;
  }

  // Validate a custom cap object {kind, seconds, turns}.
  // Returns {valid: bool, errors: string[]}.
  function validateCustomCap(cap) {
    const errors = [];
    const kind = (cap && cap.kind) || "none";
    const seconds = cap && cap.seconds;
    const turns = cap && cap.turns;
    if (!["none", "time", "turns", "both"].includes(kind)) {
      errors.push("kind must be one of: none, time, turns, both");
    }
    if (kind === "time" || kind === "both") {
      if (seconds == null) {
        errors.push("length_cap_seconds is required for kind='" + kind + "'");
      } else if (!Number.isInteger(seconds) || seconds < SECONDS_MIN || seconds > SECONDS_MAX) {
        errors.push("length_cap_seconds must be an integer in [60, 2592000]");
      }
    }
    if (kind === "turns" || kind === "both") {
      if (turns == null) {
        errors.push("length_cap_turns is required for kind='" + kind + "'");
      } else if (!Number.isInteger(turns) || turns < TURNS_MIN || turns > TURNS_MAX) {
        errors.push("length_cap_turns must be an integer in [1, 10000]");
      }
    }
    if (kind === "none" && (seconds != null || turns != null)) {
      errors.push("length_cap_seconds and length_cap_turns must be null when kind='none'");
    }
    return { valid: errors.length === 0, errors };
  }

  // Build the request body for the cap-set endpoint given a preset or
  // custom form values. Returns a plain object ready for JSON.stringify.
  // `interpretation` is optional (only required on cap-decrease re-POST).
  function buildCapPayload(preset, customValues, interpretation) {
    const presetKey = (preset || "none").toLowerCase();
    const values = presetKey !== "custom"
      ? (PRESETS[presetKey] || PRESETS.none)
      : (customValues || { kind: "none", seconds: null, turns: null });
    const payload = {
      length_cap_kind:    values.kind,
      length_cap_seconds: values.seconds,
      length_cap_turns:   values.turns,
    };
    if (interpretation != null) {
      payload.interpretation = interpretation;
    }
    return payload;
  }

  // Format a countdown for the conclude banner or settings display.
  // `seconds` is the remaining number of seconds, `turns` is the
  // remaining turn count. Both may be null when that dimension is not
  // capped.
  function formatCountdown(turns, seconds) {
    const parts = [];
    if (turns != null) {
      parts.push(turns + (turns === 1 ? " turn" : " turns"));
    }
    if (seconds != null) {
      const mins = Math.round(seconds / 60);
      parts.push(mins + (mins === 1 ? " minute" : " minutes"));
    }
    if (parts.length === 0) return "";
    return parts.join(" / ");
  }

  // Build the banner headline text for the conclude phase.
  // Per spec 025 FR-017: "Session is concluding — N turns left" / "N
  // minutes left" depending on trigger_reason.
  function formatBannerText(remaining) {
    const turns   = remaining && remaining.turns;
    const seconds = remaining && remaining.seconds;
    const countdown = formatCountdown(turns, seconds);
    if (!countdown) return "Session is concluding";
    return "Session is concluding — " + countdown + " left";
  }

  return {
    PRESETS,
    PRESET_OPTIONS,
    SECONDS_MIN,
    SECONDS_MAX,
    TURNS_MIN,
    TURNS_MAX,
    getPresetValues,
    validateCustomCap,
    buildCapPayload,
    formatCountdown,
    formatBannerText,
  };
});
