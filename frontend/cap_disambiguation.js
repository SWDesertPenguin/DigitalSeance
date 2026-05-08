/* SACP Web UI — cap-decrease disambiguation modal helpers.
 *
 * Pure-logic module for the FR-024 disambiguation modal that appears
 * when the cap-set endpoint returns HTTP 409 with
 * `error='cap_decrease_requires_interpretation'`. The facilitator
 * picks "absolute" (treat as new total cap → immediate conclude) or
 * "relative" (treat as N additional turns/seconds beyond current
 * elapsed).
 *
 * Spec 011 FR-024. Spec 025 FR-026 + contracts/cap-set-endpoint.md.
 *
 * UMD-style export — runs unchanged in the browser AND in Node.
 */

;(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof self !== "undefined" ? self : this, function () {
  // Parse the 409 response body into a structured modal model.
  // `responseBody` is the parsed JSON object from the 409.
  // Returns null if the body is not a disambiguation 409.
  function parseDisambiguation409(responseBody) {
    if (!responseBody || responseBody.error !== "cap_decrease_requires_interpretation") {
      return null;
    }
    const opts = responseBody.options || {};
    return {
      currentElapsed: responseBody.current_elapsed || {},
      submitted: responseBody.submitted || {},
      options: {
        absolute: opts.absolute || {},
        relative: opts.relative || {},
      },
    };
  }

  // Return true when `resp` looks like a 409 disambiguation response.
  function isDisambiguation409(resp) {
    return Boolean(
      resp &&
      typeof resp === "object" &&
      resp.error === "cap_decrease_requires_interpretation"
    );
  }

  // Build the request body for the re-POST given the original cap-set
  // body and the facilitator's chosen interpretation.
  // Per spec 025 FR-026: the re-POST adds `interpretation` and leaves
  // all other fields unchanged. The endpoint commits under the chosen
  // semantics (absolute: as-submitted; relative: current + submitted).
  function buildRepostBody(originalBody, interpretation) {
    if (!originalBody || typeof originalBody !== "object") return {};
    if (interpretation !== "absolute" && interpretation !== "relative") {
      throw new Error("interpretation must be 'absolute' or 'relative'");
    }
    return Object.assign({}, originalBody, { interpretation });
  }

  // Format a human-readable consequence label for each option,
  // mirroring the server-side `consequence` strings in the 409 body.
  // Accepts the raw option object from `parseDisambiguation409().options`.
  function formatOptionLabel(option, interpretation) {
    if (!option) return "";
    if (interpretation === "absolute") {
      const turns = option.effective_cap_turns;
      const secs  = option.effective_cap_seconds;
      const parts = [];
      if (turns  != null) parts.push(turns  + " total turns");
      if (secs   != null) parts.push(Math.round(secs / 60) + " total minutes");
      return "Set cap to " + (parts.join(" / ") || "(n/a)") + " → conclude phase starts now";
    }
    if (interpretation === "relative") {
      const turns = option.effective_cap_turns;
      const secs  = option.effective_cap_seconds;
      const parts = [];
      if (turns  != null) parts.push(turns  + " total turns");
      if (secs   != null) parts.push(Math.round(secs / 60) + " total minutes");
      return "Run " + (parts.join(" / ") || "(n/a)") + " from session start";
    }
    return "";
  }

  return {
    parseDisambiguation409,
    isDisambiguation409,
    buildRepostBody,
    formatOptionLabel,
  };
});
