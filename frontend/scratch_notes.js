/* SACP Web UI - facilitator-scratch pure-logic helpers (spec 024).
 *
 * Pure-logic helpers consumed by the ScratchPanel React component in
 * frontend/app.jsx per spec 011 FR-042..FR-049 (Session 2026-05-12
 * amendment). Factored out as a UMD module so debounce + markdown
 * subset rendering + note serialization can be exercised under Node
 * without a browser DOM (per frontend_polish_module_pattern memory).
 *
 * UMD-style export: window.ScratchNotes in browser, CommonJS
 * require() in Node.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ScratchNotes = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {

  // -------------------------------------------------------------------
  // Autosave debounce per spec 011 FR-044 (2-second client debounce)
  // -------------------------------------------------------------------

  function debounceAutosave(fn, waitMs) {
    if (typeof fn !== "function") {
      throw new TypeError("debounceAutosave: fn must be a function");
    }
    const wait = typeof waitMs === "number" && waitMs >= 0 ? waitMs : 2000;
    let timer = null;
    function trigger() {
      const args = Array.prototype.slice.call(arguments);
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        fn.apply(null, args);
      }, wait);
    }
    trigger.cancel = function () {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };
    trigger.pending = function () {
      return timer !== null;
    };
    return trigger;
  }

  // -------------------------------------------------------------------
  // Note serialization for the PUT body (spec 024 FR-004 OCC contract)
  // -------------------------------------------------------------------

  function serializeNoteUpdate(note) {
    if (note === null || typeof note !== "object") {
      throw new TypeError("serializeNoteUpdate: note must be an object");
    }
    if (typeof note.content !== "string") {
      throw new TypeError("serializeNoteUpdate: content must be a string");
    }
    if (typeof note.version !== "number" || note.version < 1) {
      throw new TypeError("serializeNoteUpdate: version must be >= 1");
    }
    return { content: note.content, version: note.version };
  }

  // -------------------------------------------------------------------
  // Markdown subset render: bold, italic, inline code, links, headings,
  // bullet lists, code blocks. Plain text escapes HTML first. Output is
  // a single HTML string consumed by dangerouslySetInnerHTML (after a
  // DOMPurify pass at render time in the React component).
  // -------------------------------------------------------------------

  function _escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function _renderInline(line) {
    let out = _escapeHtml(line);
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[\s])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
    out = out.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>',
    );
    return out;
  }

  function _renderHeading(line) {
    const match = line.match(/^(#{1,6})\s+(.*)$/);
    if (!match) return null;
    const level = match[1].length;
    return "<h" + level + ">" + _renderInline(match[2]) + "</h" + level + ">";
  }

  function _renderBulletItem(line) {
    const match = line.match(/^[-*]\s+(.*)$/);
    if (!match) return null;
    return "<li>" + _renderInline(match[1]) + "</li>";
  }

  function renderMarkdownSubset(source) {
    if (typeof source !== "string") return "";
    const lines = source.split(/\r?\n/);
    const out = [];
    let inCodeBlock = false;
    let inList = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith("```")) {
        if (inCodeBlock) { out.push("</code></pre>"); inCodeBlock = false; }
        else { out.push("<pre><code>"); inCodeBlock = true; }
        continue;
      }
      if (inCodeBlock) { out.push(_escapeHtml(line)); continue; }
      const heading = _renderHeading(line);
      if (heading) {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push(heading);
        continue;
      }
      const bullet = _renderBulletItem(line);
      if (bullet) {
        if (!inList) { out.push("<ul>"); inList = true; }
        out.push(bullet);
        continue;
      }
      if (inList) { out.push("</ul>"); inList = false; }
      if (line.trim() === "") { out.push(""); continue; }
      out.push("<p>" + _renderInline(line) + "</p>");
    }
    if (inList) out.push("</ul>");
    if (inCodeBlock) out.push("</code></pre>");
    return out.join("\n");
  }

  // -------------------------------------------------------------------
  // Scope detection per spec 024 FR-015 + spec 011 FR-049. The FR-002
  // response carries `scope` and `account_id`; the SPA renders a chip
  // showing "Account-scoped" vs "Session-scoped" so the facilitator
  // knows whether their notes survive archive.
  // -------------------------------------------------------------------

  function describeScope(scope) {
    if (scope === "account") {
      return {
        chipText: "Account-scoped",
        chipClass: "scratch-scope-account",
        explanation: "Notes survive session archive.",
      };
    }
    return {
      chipText: "Session-scoped",
      chipClass: "scratch-scope-session",
      explanation: "Notes are deleted when the session is archived.",
    };
  }

  // -------------------------------------------------------------------
  // Promoted marker per spec 011 FR-045 — note rows with promoted_at
  // gain a visual indicator linking to the resulting transcript turn.
  // -------------------------------------------------------------------

  function formatPromotedMarker(note) {
    if (!note || note.promoted_at == null) return null;
    const turn = note.promoted_message_turn;
    const at = note.promoted_at;
    return {
      promoted: true,
      turn: typeof turn === "number" ? turn : null,
      promotedAt: at,
    };
  }

  // -------------------------------------------------------------------
  // Summary preview per spec 005 §FR-005 structured shape. The FR-002
  // payload ships a `content` JSON string and a server-side
  // `content_preview` truncated to 200 chars. The pure-logic helpers
  // here extract the four structured sections for the expanded view.
  // -------------------------------------------------------------------

  function parseSummaryContent(rawContent) {
    if (typeof rawContent !== "string" || rawContent.length === 0) {
      return { narrative: "", decisions: [], open_questions: [], key_positions: [] };
    }
    try {
      const parsed = JSON.parse(rawContent);
      if (parsed === null || typeof parsed !== "object") {
        return { narrative: String(rawContent), decisions: [], open_questions: [], key_positions: [] };
      }
      return {
        narrative: typeof parsed.narrative === "string" ? parsed.narrative : "",
        decisions: Array.isArray(parsed.decisions) ? parsed.decisions : [],
        open_questions: Array.isArray(parsed.open_questions) ? parsed.open_questions : [],
        key_positions: Array.isArray(parsed.key_positions) ? parsed.key_positions : [],
      };
    } catch (_e) {
      return { narrative: rawContent, decisions: [], open_questions: [], key_positions: [] };
    }
  }

  function formatTurnRange(summary, prior) {
    // Spec 011 FR-047 — summary row displays turn range (first..last).
    // Prior summary's turn_number is the lower bound; first summary
    // starts at turn 1.
    const last = summary && typeof summary.turn_number === "number" ? summary.turn_number : null;
    const first = prior && typeof prior.turn_number === "number" ? prior.turn_number + 1 : 1;
    if (last == null) return "";
    if (first > last) return `turn ${last}`;
    return `turn ${first}-${last}`;
  }

  // -------------------------------------------------------------------
  // Review-gate disposition labels per spec 011 FR-048 + spec 029 audit
  // labels. The action key uses underscore form; we surface a friendly
  // disposition string for the row header.
  // -------------------------------------------------------------------

  function reviewGateDisposition(action) {
    if (action === "review_gate_approve") return "Approved (verbatim)";
    if (action === "review_gate_edit") return "Approved (edited)";
    if (action === "review_gate_reject") return "Rejected";
    return action || "(unknown)";
  }

  return {
    debounceAutosave: debounceAutosave,
    serializeNoteUpdate: serializeNoteUpdate,
    renderMarkdownSubset: renderMarkdownSubset,
    describeScope: describeScope,
    formatPromotedMarker: formatPromotedMarker,
    parseSummaryContent: parseSummaryContent,
    formatTurnRange: formatTurnRange,
    reviewGateDisposition: reviewGateDisposition,
  };
});
