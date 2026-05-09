/* SACP Web UI - audit-log timestamp formatter (spec 029 FR-009).
 *
 * Frontend mirror of src/orchestrator/time_format.py per
 * shared-module-contracts.md §2. Loaded ahead of app.jsx via <script>
 * in index.html; consumed by the AuditLogPanel for primary UTC
 * display, with formatLocale + formatRelative used by the hover overlay.
 *
 * Parity gate (scripts/check_time_format_parity.py) enforces that
 * formatIso output byte-equals the Python format_iso output for the
 * same UTC instant. formatLocale and formatRelative are intentionally
 * not parity-checked - their output may vary across browsers (locale
 * conventions, RTL handling).
 *
 * UMD-style export so the same file runs unchanged in the browser
 * (attaches to window.TimeFormat) AND in Node (CommonJS) for tests.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.TimeFormat = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Coerce the supported input union into a Date.
  // Accepts: ISO-8601 string, Date object, or Unix epoch milliseconds.
  // Throws on anything else (null, undefined, naive numeric strings).
  function _toDate(timestamp) {
    if (timestamp instanceof Date) {
      if (Number.isNaN(timestamp.getTime())) {
        throw new TypeError("formatIso received an Invalid Date");
      }
      return timestamp;
    }
    if (typeof timestamp === "number" && Number.isFinite(timestamp)) {
      return new Date(timestamp);
    }
    if (typeof timestamp === "string" && timestamp.length > 0) {
      const d = new Date(timestamp);
      if (Number.isNaN(d.getTime())) {
        throw new TypeError("formatIso could not parse string: " + timestamp);
      }
      return d;
    }
    throw new TypeError(
      "formatIso requires Date, ISO-8601 string, or epoch ms; got " +
        typeof timestamp,
    );
  }

  function _pad(n, width) {
    const s = String(n);
    if (s.length >= width) return s;
    return "0".repeat(width - s.length) + s;
  }

  // YYYY-MM-DDTHH:MM:SS.sssZ - byte-equal to Python format_iso for the
  // same UTC instant. Always renders in UTC; never honours the local zone.
  function formatIso(timestamp) {
    const d = _toDate(timestamp);
    return (
      _pad(d.getUTCFullYear(), 4) +
      "-" + _pad(d.getUTCMonth() + 1, 2) +
      "-" + _pad(d.getUTCDate(), 2) +
      "T" + _pad(d.getUTCHours(), 2) +
      ":" + _pad(d.getUTCMinutes(), 2) +
      ":" + _pad(d.getUTCSeconds(), 2) +
      "." + _pad(d.getUTCMilliseconds(), 3) +
      "Z"
    );
  }

  // Browser locale-aware secondary display; used by the hover overlay.
  // Falls back to a stable ISO string if Intl.DateTimeFormat is missing
  // (very old runtimes / restricted execution contexts) so the helper
  // never throws purely because the environment lacks Intl support.
  function formatLocale(timestamp) {
    const d = _toDate(timestamp);
    if (typeof Intl === "undefined" || typeof Intl.DateTimeFormat !== "function") {
      return d.toISOString();
    }
    try {
      const fmt = new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
      });
      return fmt.format(d);
    } catch (_e) {
      return d.toISOString();
    }
  }

  // Buckets for relative-time output. Order matters - first matching
  // bucket wins, so ensure each entry is descending in seconds.
  const _RELATIVE_BUCKETS = [
    { unit: "year",   seconds: 60 * 60 * 24 * 365 },
    { unit: "month",  seconds: 60 * 60 * 24 * 30  },
    { unit: "week",   seconds: 60 * 60 * 24 * 7   },
    { unit: "day",    seconds: 60 * 60 * 24       },
    { unit: "hour",   seconds: 60 * 60            },
    { unit: "minute", seconds: 60                 },
    { unit: "second", seconds: 1                  },
  ];

  // "3 minutes ago" / "in 5 hours" / "just now". Uses Intl.RelativeTimeFormat
  // when available; falls back to a small English-only formatter otherwise.
  function formatRelative(timestamp, nowMs) {
    const d = _toDate(timestamp);
    const now = typeof nowMs === "number" ? nowMs : Date.now();
    const deltaSec = Math.round((d.getTime() - now) / 1000);
    if (deltaSec === 0) return "just now";
    const absSec = Math.abs(deltaSec);
    let bucket = _RELATIVE_BUCKETS[_RELATIVE_BUCKETS.length - 1];
    let value = deltaSec;
    for (const b of _RELATIVE_BUCKETS) {
      if (absSec >= b.seconds) {
        bucket = b;
        value = Math.round(deltaSec / b.seconds);
        break;
      }
    }
    if (typeof Intl !== "undefined" && typeof Intl.RelativeTimeFormat === "function") {
      try {
        const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
        return rtf.format(value, bucket.unit);
      } catch (_e) {
        /* fall through */
      }
    }
    const absVal = Math.abs(value);
    const unit = bucket.unit + (absVal === 1 ? "" : "s");
    return value < 0 ? absVal + " " + unit + " ago" : "in " + absVal + " " + unit;
  }

  return { formatIso, formatLocale, formatRelative };
});
