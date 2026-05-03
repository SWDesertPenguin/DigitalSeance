/* SACP Web UI — Phase 2a complete (US1 + US2 + US3 + US8).
 *
 * Single-file React SPA. All components live here; will split into
 * frontend/components/*.jsx when this file crosses ~2000 lines.
 *
 * What's here:
 *   US1 (T050–T057)  facilitator login + session view + message input +
 *                    session controls + add-participant modal
 *   US2 (T070–T073)  participant role gating, SelfControls panel,
 *                    pending-participant filter
 *   US3 (T080–T084)  resilient WebSocket: exponential backoff 1→30s,
 *                    ping/pong heartbeat, 4401/4403 force re-login,
 *                    connection indicator in header
 *   US8 (T090–T093)  hardened markdown: images neutralized, javascript:
 *                    links blocked, raw HTML stripped, invisible
 *                    Unicode unveiled with per-message count badge
 *
 * Deferred: T058/T074/T085/T094 Playwright e2e — needs pytest-playwright
 * + browser install step scripted before these can run in CI.
 */

const { useState, useEffect, useReducer, useCallback, useRef, useMemo } = React;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// MCP tool calls now go through the Web UI's same-origin proxy at
// /api/mcp/<path>. The proxy attaches the bearer server-side from the
// session store (audit H-02). The SPA no longer holds the bearer in JS.
const MCP_PROXY_PREFIX = "/api/mcp";

const WS_BASE = (() => {
  const { protocol, host } = window.location;
  const wsProto = protocol === "https:" ? "wss:" : "ws:";
  return `${wsProto}//${host}`;
})();

// WebSocket close codes from the v1 contract.
const WS_CLOSE_UNAUTHENTICATED = 4401;
const WS_CLOSE_FORBIDDEN = 4403;

const ROUTING_PREFERENCES = [
  "always",
  "review_gate",
  "delegate_low",
  "domain_gated",
  "burst",
  "observer",
  "addressed_only",
  "human_only",
];

// Float noise from Postgres REAL columns (e.g. 0.18000000715255737) looked
// awful next to clean spend totals. Clamp to 4 decimals and strip trailing
// zeros so $0.18 stays $0.18 but $0.0041 keeps precision.
function fmtDollars(n) {
  if (n == null) return "";
  const num = Number(n);
  if (!Number.isFinite(num)) return "";
  return num.toFixed(4).replace(/\.?0+$/, "") || "0";
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function _fetchJson(url, opts = {}) {
  let res;
  try {
    res = await fetch(url, opts);
  } catch (e) {
    // Browser fetch rejects with TypeError on connection failures (DNS, offline,
    // server down). Default messages are unhelpful ("NetworkError when attempting
    // to fetch resource" / "Failed to fetch"). Rephrase before bubbling.
    if (e instanceof TypeError) {
      throw new Error("Network unavailable — check your connection or that the SACP server is reachable.");
    }
    throw e;
  }
  const contentType = res.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = typeof body === "object" && body?.detail ? body.detail : body;
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return body;
}

function mcpCall(path, { method = "GET", body = null } = {}) {
  const headers = { "Content-Type": "application/json", "X-SACP-Request": "1" };
  const opts = { method, headers, credentials: "include" };
  if (body !== null) opts.body = JSON.stringify(body);
  return _fetchJson(`${MCP_PROXY_PREFIX}${path}`, opts);
}

function uiCall(path, { method = "GET", body = null } = {}) {
  const headers = { "Content-Type": "application/json", "X-SACP-Request": "1" };
  const opts = { method, headers, credentials: "include" };
  if (body !== null) opts.body = JSON.stringify(body);
  return _fetchJson(path, opts);
}

// ---------------------------------------------------------------------------
// Security — markdown rendering with image/link/HTML overrides + invisible
// Unicode unveiling. Covers US8 (T090–T092).
// ---------------------------------------------------------------------------

const INVISIBLE_CHAR_LABELS = {
  "\u200b": "ZWS",
  "\u200c": "ZWNJ",
  "\u200d": "ZWJ",
  "\u200e": "LRM",
  "\u200f": "RLM",
  "\u202a": "LRE",
  "\u202b": "RLE",
  "\u202c": "PDF",
  "\u202d": "LRO",
  "\u202e": "RLO",
  "\u2066": "LRI",
  "\u2067": "RLI",
  "\u2068": "FSI",
  "\u2069": "PDI",
  "\ufeff": "BOM",
};
const INVISIBLE_REGEX = /[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;" }[c]
  ));
}

function countInvisibles(s) {
  return ((s || "").match(INVISIBLE_REGEX) || []).length;
}

function unveilInvisibles(html) {
  return html.replace(INVISIBLE_REGEX, (ch) => {
    const label = INVISIBLE_CHAR_LABELS[ch] || "INV";
    return `<span class="invisible-marker" title="invisible char">[${label}]</span>`;
  });
}

function buildHardenedRenderer() {
  const renderer = new marked.Renderer();

  // Images: neutralized entirely — no network fetch, no alt-text XSS.
  renderer.image = (hrefOrToken, _title, text) => {
    const alt = typeof hrefOrToken === "object" && hrefOrToken !== null
      ? (hrefOrToken.text || "")
      : (text || "");
    return `<span class="neutralized-image">[Image: ${escapeHtml(alt)}]</span>`;
  };

  // Links: block javascript: / data: / vbscript: / file: schemes.
  renderer.link = (hrefOrToken, _title, text) => {
    const href = typeof hrefOrToken === "object" && hrefOrToken !== null
      ? (hrefOrToken.href || "")
      : hrefOrToken;
    const body = typeof hrefOrToken === "object" && hrefOrToken !== null
      ? (hrefOrToken.text || "")
      : (text || "");
    const safe = String(href || "").trim();
    if (/^(javascript|data|vbscript|file):/i.test(safe)) {
      return `<span class="blocked-link" title="blocked scheme">⚠ ${escapeHtml(body)}</span>`;
    }
    return `<a href="${escapeHtml(safe)}" target="_blank" rel="noreferrer noopener">${escapeHtml(body)}</a>`;
  };

  // Raw HTML in markdown is stripped.
  renderer.html = () => "";

  return renderer;
}

const _DOMPURIFY_CONFIG = {
  ALLOWED_TAGS: [
    "p", "br", "hr", "strong", "em", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "span", "table", "thead", "tbody", "tr", "th", "td",
  ],
  ALLOWED_ATTR: ["href", "target", "rel", "class", "title"],
  ALLOW_DATA_ATTR: false,
};

function renderMarkdown(content) {
  if (!content) return "";
  const renderer = buildHardenedRenderer();
  const raw = marked.parse(content, { renderer, breaks: true });
  const cleaned = DOMPurify.sanitize(raw, _DOMPURIFY_CONFIG);
  return unveilInvisibles(cleaned);
}

// ---------------------------------------------------------------------------
// State reducer — handles state_snapshot + delta WS events
// ---------------------------------------------------------------------------

function _prependResolved(resolved, openList, event) {
  const source = openList.find((p) => p.id === event.proposal_id);
  if (!source) return resolved;
  const entry = { ...source, status: event.status || "resolved", tally: event.tally || source.tally };
  return [entry, ...resolved].slice(0, 50);
}

function initialState() {
  return {
    session: null,
    me: null,
    participants: [],
    messages: [],
    pendingDrafts: [],
    openProposals: [],
    resolvedProposals: [],
    latestSummary: null,
    convergenceScores: [],
    auditEntries: [],      // Phase 2b: fed by T252 audit_entry WS events
    skipReasons: {},       // { participant_id: [{reason, timestamp}, ...] } (last 3 per pid)
    // Open AI questions: list of {key, participant_id, turn_number,
    // questions: [str], at}. Transient (not persisted server-side).
    // Dismissed manually via "✓ resolved" button.
    openAIQuestions: [],
    // Exit requests: { participant_id: {turn_number, phrase, at} }.
    // The facilitator can "honor" (flip routing to observer) or dismiss.
    aiExitRequests: {},
    wsState: "connecting",
    authError: null,
    errors: [],
  };
}

function reducer(state, action) {
  switch (action.type) {
    case "ws_state":
      return { ...state, wsState: action.value };
    case "auth_error":
      return { ...state, authError: action.message || "Session expired" };
    case "clear_auth_error":
      return { ...state, authError: null };
    case "state_snapshot": {
      const e = action.event;
      return {
        ...state,
        session: e.session || null,
        me: e.me || null,
        participants: e.participants || [],
        messages: e.messages || [],
        pendingDrafts: e.pending_drafts || [],
        openProposals: e.open_proposals || [],
        latestSummary: e.latest_summary || null,
        convergenceScores: e.convergence_scores || [],
      };
    }
    case "message": {
      const incoming = action.event.message;
      const key = (m) => `${m.turn_number}:${m.speaker_id}`;
      const incomingKey = key(incoming);
      const others = state.messages.filter((m) => key(m) !== incomingKey);
      const currentTurn = state.session?.current_turn ?? 0;
      const nextTurn = Math.max(currentTurn, incoming.turn_number || 0);
      return {
        ...state,
        messages: [...others, incoming].sort((a, b) => a.turn_number - b.turn_number),
        session: state.session ? { ...state.session, current_turn: nextTurn } : state.session,
      };
    }
    case "participant_update": {
      const updated = action.event.participant;
      const others = state.participants.filter((p) => p.id !== updated.id);
      // If the update is for the current user, also refresh state.me so
      // isFacilitator / role-gated UI responds to promotions/demotions
      // (e.g. transfer_facilitator) without a refresh.
      const isSelf = state.me?.participant_id === updated.id;
      const nextMe = isSelf ? { ...state.me, role: updated.role } : state.me;
      return { ...state, participants: [...others, updated], me: nextMe };
    }
    case "participant_removed": {
      // Row was hard-deleted server-side (reject_participant). Drop it
      // from local state so the pending/participant lists refresh
      // without a page reload.
      const removedId = action.event.participant_id;
      return {
        ...state,
        participants: state.participants.filter((p) => p.id !== removedId),
      };
    }
    case "participant_restore":
      // Client-only: re-insert a participant we optimistically removed
      // when the server call turned out to fail.
      return {
        ...state,
        participants: [
          ...state.participants.filter((p) => p.id !== action.participant.id),
          action.participant,
        ],
      };
    case "session_status_changed":
      return { ...state, session: { ...(state.session || {}), status: action.event.status } };
    case "session_updated":
      return { ...state, session: { ...(state.session || {}), ...(action.event.updates || {}) } };
    case "loop_status":
      return { ...state, session: { ...(state.session || {}), loop_running: action.event.running } };
    case "convergence_update":
      return {
        ...state,
        convergenceScores: [...state.convergenceScores, action.event.point].slice(-50),
      };
    case "review_gate_staged":
      return { ...state, pendingDrafts: [...state.pendingDrafts, action.event.draft] };
    case "review_gate_resolved":
      return {
        ...state,
        pendingDrafts: state.pendingDrafts.filter((d) => d.id !== action.event.draft_id),
      };
    case "summary_created":
      return { ...state, latestSummary: action.event.summary };
    case "ai_question_opened": {
      const { participant_id, turn_number, questions, at } = action.event;
      const entries = (questions || []).map((q, i) => ({
        key: `${participant_id}-${turn_number}-${i}`,
        participant_id,
        turn_number,
        question: q,
        at,
      }));
      return { ...state, openAIQuestions: [...state.openAIQuestions, ...entries] };
    }
    case "ai_question_dismissed":
      return {
        ...state,
        openAIQuestions: state.openAIQuestions.filter((q) => q.key !== action.key),
      };
    case "ai_exit_requested": {
      const { participant_id, turn_number, phrase, at } = action.event;
      return {
        ...state,
        aiExitRequests: {
          ...state.aiExitRequests,
          [participant_id]: { turn_number, phrase, at },
        },
      };
    }
    case "ai_exit_dismissed": {
      const next = { ...state.aiExitRequests };
      delete next[action.participant_id];
      return { ...state, aiExitRequests: next };
    }
    case "audit_entry":
      // T252: keep a ring buffer of the last 100 facilitator actions.
      return {
        ...state,
        auditEntries: [action.event.entry, ...state.auditEntries].slice(0, 100),
      };
    case "turn_skipped": {
      // US10 T141: feed the health-badge tooltip.
      const { participant_id: pid, reason, turn_number } = action.event;
      const prior = state.skipReasons[pid] || [];
      return {
        ...state,
        skipReasons: {
          ...state.skipReasons,
          [pid]: [{ reason, turn_number }, ...prior].slice(0, 3),
        },
      };
    }
    case "seed_audit_entries":
      return { ...state, auditEntries: action.entries.slice(0, 100) };
    case "seed_proposals":
      return { ...state, openProposals: action.proposals, resolvedProposals: action.resolved || [] };
    case "proposal_created":
      return {
        ...state,
        openProposals: [...state.openProposals, { ...action.event.proposal, tally: { accept: 0, reject: 0, abstain: 0 } }],
      };
    case "proposal_voted":
      return {
        ...state,
        openProposals: state.openProposals.map((p) =>
          p.id === action.event.proposal_id ? { ...p, tally: action.event.tally } : p,
        ),
      };
    case "proposal_resolved":
      return {
        ...state,
        openProposals: state.openProposals.filter((p) => p.id !== action.event.proposal_id),
        resolvedProposals: _prependResolved(state.resolvedProposals, state.openProposals, action.event),
      };
    case "error": {
      // Dedupe by code+message — when the loop keeps retrying a bad
      // key it would otherwise pile up identical toasts faster than
      // the user can dismiss them. Cap at 5 so a single misconfigured
      // session can't fill the screen with toasts. Newest stays on top.
      const next = { code: action.event.code, message: action.event.message };
      const isDup = state.errors.some(
        (e) => e.code === next.code && e.message === next.message,
      );
      if (isDup) return state;
      return { ...state, errors: [next, ...state.errors].slice(0, 5) };
    }
    case "clear_error":
      return { ...state, errors: state.errors.filter((_, i) => i !== action.index) };
    default:
      console.warn("[ws] unknown event type:", action?.type);
      return state;
  }
}

// ---------------------------------------------------------------------------
// WebSocket client — US3 resilience.
//   * 1→30s exponential backoff reconnect
//   * 30s ping heartbeat, pong round-trip expected back
//   * 4401/4403 close codes stop reconnect and surface re-login banner
//   * onEvent held in a ref so callback churn doesn't retrigger connects
// ---------------------------------------------------------------------------

function useWebSocket(sessionId, onEvent, onAuthExpired) {
  const [state, setState] = useState("connecting");
  const eventRef = useRef(onEvent);
  const authExpiredRef = useRef(onAuthExpired);

  useEffect(() => { eventRef.current = onEvent; }, [onEvent]);
  useEffect(() => { authExpiredRef.current = onAuthExpired; }, [onAuthExpired]);

  useEffect(() => {
    if (!sessionId) return undefined;
    let closed = false;
    let wsInstance = null;
    let retryTimer = null;
    let heartbeatTimer = null;
    let retries = 0;

    const backoffMs = () => Math.min(30000, 1000 * Math.pow(2, Math.max(0, retries - 1)));

    const stopHeartbeat = () => {
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
    };

    const startHeartbeat = (ws) => {
      stopHeartbeat();
      heartbeatTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ v: 1, type: "ping" }));
        }
      }, 30000);
    };

    const scheduleReconnect = () => {
      if (closed) return;
      retries += 1;
      const ms = backoffMs();
      setState("reconnecting");
      retryTimer = setTimeout(connect, ms);
    };

    const connect = () => {
      const ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);
      wsInstance = ws;
      setState(retries > 0 ? "reconnecting" : "connecting");

      ws.onopen = () => {
        retries = 0;
        setState("open");
        startHeartbeat(ws);
      };
      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data);
          if (event?.type === "pong") return;
          eventRef.current?.(event);
        } catch (e) {
          console.warn("[ws] bad frame:", e);
        }
      };
      ws.onclose = (ev) => {
        stopHeartbeat();
        if (closed) return;
        if (ev.code === WS_CLOSE_UNAUTHENTICATED || ev.code === WS_CLOSE_FORBIDDEN) {
          setState("closed");
          authExpiredRef.current?.(ev.code);
          return;
        }
        scheduleReconnect();
      };
      ws.onerror = () => { /* close event will follow */ };
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      stopHeartbeat();
      if (wsInstance) wsInstance.close();
    };
  }, [sessionId]);

  return state;
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function AuthGate({ banner, onLogin }) {
  // US11 guest landing — three paths: Sign in / Create / Request to join.
  // All three ultimately call onLogin(result) once we hold a live cookie.
  const [mode, setMode] = useState("choose");
  const goLogin = useCallback((result) => onLogin(result), [onLogin]);
  return (
    <main className="auth-gate">
      <h1>SACP Web UI</h1>
      {banner && <div className="banner banner-warn">{banner}</div>}
      {mode === "choose" && <GuestChoose onPick={setMode} />}
      {mode === "signin" && <SignInForm onLogin={goLogin} onBack={() => setMode("choose")} />}
      {mode === "create" && <CreateSessionForm onLogin={goLogin} onBack={() => setMode("choose")} />}
      {mode === "join" && <RequestJoinForm onLogin={goLogin} onBack={() => setMode("choose")} />}
      {mode === "invite" && <RedeemInviteForm onLogin={goLogin} onBack={() => setMode("choose")} />}
    </main>
  );
}

function GuestChoose({ onPick }) {
  return (
    <div className="guest-choose">
      <p className="dim">Pick a path to get started.</p>
      <button type="button" className="big-btn" onClick={() => onPick("signin")}>
        Sign in with a token
      </button>
      <button type="button" className="big-btn" onClick={() => onPick("create")}>
        Create a new session
      </button>
      <button type="button" className="big-btn" onClick={() => onPick("join")}>
        Request to join a session
      </button>
      <button type="button" className="big-btn" onClick={() => onPick("invite")}>
        Redeem an invite code
      </button>
    </div>
  );
}

function RedeemInviteForm({ onLogin, onBack }) {
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (ev) => {
    ev.preventDefault();
    if (!token.trim() || !name.trim()) return;
    setBusy(true); setError(null);
    try {
      const result = await mcpCall("/tools/session/redeem_invite", {
        method: "POST",
        body: { invite_token: token.trim(), display_name: name.trim() },
      });
      onLogin(await _loginWithToken(result.auth_token));
    } catch (e) { setError(e.message || "Redeem failed"); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="auth-form">
      <p className="dim">Paste the invite code the facilitator gave you.</p>
      <input type="text" placeholder="invite code" value={token}
        onChange={(ev) => setToken(ev.target.value)} autoFocus />
      <input type="text" placeholder="your display name" value={name}
        onChange={(ev) => setName(ev.target.value)} maxLength={64} />
      <div className="auth-actions">
        <button type="button" className="link-btn" onClick={onBack}>← back</button>
        <button type="submit" className={busy ? "busy" : ""}
          disabled={busy || !token.trim() || !name.trim()}>
          {busy ? "Redeeming" : "Redeem"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  );
}

async function _loginWithToken(token) {
  return uiCall("/login", { method: "POST", body: { token } });
}

function SignInForm({ onLogin, onBack }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (ev) => {
    ev.preventDefault();
    if (!token.trim()) return;
    setBusy(true); setError(null);
    try { onLogin(await _loginWithToken(token.trim())); }
    catch (e) { setError(e.message || "Login failed"); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="auth-form">
      <p className="dim">Paste your bearer token.</p>
      <input type="password" placeholder="bearer token" value={token}
        onChange={(ev) => setToken(ev.target.value)} autoFocus />
      <div className="auth-actions">
        <button type="button" className="link-btn" onClick={onBack}>← back</button>
        <button type="submit" className={busy ? "busy" : ""} disabled={busy || !token.trim()}>
          {busy ? "Signing in" : "Sign in"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  );
}

function CreateSessionForm({ onLogin, onBack }) {
  const [name, setName] = useState("");
  const [sessionName, setSessionName] = useState("");
  const [reveal, setReveal] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (ev) => {
    ev.preventDefault();
    if (!name.trim()) return;
    setBusy(true); setError(null);
    try {
      const result = await mcpCall("/tools/session/create", {
        method: "POST",
        body: {
          display_name: `Facilitator-${name.trim()}`,
          name: sessionName.trim(),
        },
      });
      setReveal(result);
    } catch (e) { setError(e.message || "Create failed"); }
    finally { setBusy(false); }
  };
  const proceed = async () => {
    if (!reveal?.auth_token) return;
    try { onLogin(await _loginWithToken(reveal.auth_token)); }
    catch (e) { setError(e.message || "Login failed"); }
  };
  if (reveal) return <TokenRevealModal result={reveal} onProceed={proceed} />;
  return (
    <form onSubmit={submit} className="auth-form">
      <p className="dim">Your name (we'll prefix it with "Facilitator-").</p>
      <input type="text" placeholder="your name" value={name}
        onChange={(ev) => setName(ev.target.value)} autoFocus maxLength={64} />
      <p className="dim">Session name (optional — auto-generated if blank).</p>
      <input type="text" placeholder="(optional — auto-generated if blank)" value={sessionName}
        onChange={(ev) => setSessionName(ev.target.value)} maxLength={120} />
      <div className="auth-actions">
        <button type="button" className="link-btn" onClick={onBack}>← back</button>
        <button type="submit" className={busy ? "busy" : ""} disabled={busy || !name.trim()}>
          {busy ? "Creating" : "Create session"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  );
}

function TokenRevealModal({ result, onProceed }) {
  return (
    <div className="token-reveal">
      <h2>Session created</h2>
      <p className="dim">
        Save this token. It's your API key — you'll need it for reconnects,
        MCP, Swagger, and CLI tools. It won't be shown again.
      </p>
      <CopyableToken token={result.auth_token} />
      <div className="dim token-meta">
        {result.name && <div>Session: <code>{result.name}</code></div>}
        <div>Session ID: <code>{result.session_id}</code></div>
        <div>Facilitator ID: <code>{result.facilitator_id}</code></div>
      </div>
      <button type="button" onClick={onProceed} className="big-btn">
        I saved it — enter the session
      </button>
    </div>
  );
}

function AddedParticipantTokenModal({ entry, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal token-reveal" onClick={(ev) => ev.stopPropagation()}>
        <h2>Token for {entry.display_name}</h2>
        <p className="dim">
          Give this to them privately — it's their API key, and it won't be
          shown again. They'll paste it into the login screen to join.
        </p>
        <CopyableToken token={entry.token} />
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

function CopyableToken({ token }) {
  // Shared clipboard surface for token + invite display. navigator.clipboard
  // often fails silently under LAN/HTTP or strict CSP; we fall back to a
  // selectable <input readonly> so users can always Ctrl+C manually.
  const [copied, setCopied] = useState(false);
  const inputRef = useRef(null);
  const copy = async () => {
    const value = token || "";
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      return;
    } catch { /* fall through to manual select */ }
    try {
      inputRef.current?.focus();
      inputRef.current?.select();
      document.execCommand?.("copy");
      setCopied(true);
    } catch { /* keep silent — user can still Ctrl+C */ }
  };
  return (
    <div className="token-row">
      <input ref={inputRef} type="text" readOnly value={token || ""} onClick={(e) => e.target.select()} />
      <button type="button" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
    </div>
  );
}

function RequestJoinForm({ onLogin, onBack }) {
  const [sid, setSid] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (ev) => {
    ev.preventDefault();
    if (!sid.trim() || !name.trim()) return;
    setBusy(true); setError(null);
    try {
      const result = await mcpCall("/tools/session/request_join", {
        method: "POST",
        body: { session_id: sid.trim(), display_name: name.trim() },
      });
      onLogin(await _loginWithToken(result.auth_token));
    } catch (e) {
      const msg = e.message || "Request failed";
      if (msg.startsWith("404")) {
        setError("No active session with that ID. Check the ID and try again.");
      } else if (msg.startsWith("409")) {
        setError("That session isn't accepting new joins right now (paused or archived).");
      } else {
        setError(msg);
      }
    }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="auth-form">
      <p className="dim">Enter the session ID and your display name.</p>
      <input type="text" placeholder="session id" value={sid}
        onChange={(ev) => setSid(ev.target.value)} autoFocus />
      <input type="text" placeholder="your display name" value={name}
        onChange={(ev) => setName(ev.target.value)} maxLength={64} />
      <div className="auth-actions">
        <button type="button" className="link-btn" onClick={onBack}>← back</button>
        <button type="submit" className={busy ? "busy" : ""} disabled={busy || !sid.trim() || !name.trim()}>
          {busy ? "Requesting" : "Request to join"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </form>
  );
}

function Header({ session, me, wsState, onExport, theme, onToggleTheme, onRename, isFacilitator }) {
  const dotColor =
    wsState === "open" ? "var(--ok)" :
    wsState === "reconnecting" ? "var(--warning)" :
    "var(--danger)";
  const dotTitle =
    wsState === "open" ? "connected" :
    wsState === "reconnecting" ? "reconnecting…" :
    wsState === "closed" ? "disconnected" : wsState;
  return (
    <header className="app-header">
      <div className="header-left">
        <SessionNameDisplay session={session} canEdit={isFacilitator} onRename={onRename} />
        <span className={`status-badge status-${session?.status || "unknown"}`}>
          {session?.status || "?"}
        </span>
        <span
          className={`loop-badge loop-${session?.loop_running ? "running" : "idle"}`}
          title={session?.loop_running ? "turn loop is running" : "turn loop is idle"}
        >
          loop: {session?.loop_running ? "running" : "idle"}
        </span>
      </div>
      <div className="header-center">
        <span>Turn {session?.current_turn ?? 0}</span>
      </div>
      <div className="header-right">
        <button className="icon-btn" onClick={() => onExport("markdown")} title="Export markdown">
          ⬇ .md
        </button>
        <button className="icon-btn" onClick={() => onExport("json")} title="Export JSON">
          ⬇ .json
        </button>
        <button className="icon-btn" onClick={onToggleTheme} title="Toggle theme">
          {theme === "light" ? "🌙" : "☀"}
        </button>
        <span className="ws-indicator" style={{ backgroundColor: dotColor }} title={dotTitle} />
        <span className="me">{me?.participant_id}</span>
      </div>
    </header>
  );
}

function SessionNameDisplay({ session, canEdit, onRename }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session?.name || "");
  useEffect(() => { if (!editing) setDraft(session?.name || ""); }, [session?.name, editing]);
  const save = async () => {
    const next = draft.trim();
    if (!next || next === session?.name) { setEditing(false); return; }
    try { await onRename(next); } finally { setEditing(false); }
  };
  if (editing) {
    return (
      <span className="session-name edit">
        <input value={draft} onChange={(ev) => setDraft(ev.target.value)}
          onBlur={save} autoFocus maxLength={128}
          onKeyDown={(ev) => {
            if (ev.key === "Enter") save();
            if (ev.key === "Escape") setEditing(false);
          }} />
      </span>
    );
  }
  return (
    <strong
      className={`session-name${canEdit ? " editable" : ""}`}
      title={canEdit ? "click to rename session" : session?.name}
      onClick={() => canEdit && setEditing(true)}
    >
      {session?.name || "…"}
    </strong>
  );
}

function ErrorToasts({ errors, onDismiss }) {
  // Auto-fade each toast after 10s so a transient provider blip doesn't
  // stick around forever even if the operator misses it. Click the X to
  // dismiss sooner. The reducer also dedupes by code+message and caps
  // at 5 so the loop's retry-storm can't drown out user clicks.
  useEffect(() => {
    if (!errors || errors.length === 0) return;
    const timer = setTimeout(() => onDismiss(errors.length - 1), 10_000);
    return () => clearTimeout(timer);
  }, [errors, onDismiss]);
  if (!errors || errors.length === 0) return null;
  return (
    <div className="error-toasts">
      {errors.map((err, i) => (
        <div key={`${err.code}-${err.message}-${i}`}
             className={`error-toast toast-${err.code || "generic"}`}>
          <div className="toast-body">
            <strong>{err.code || "error"}</strong>
            <span>{err.message}</span>
          </div>
          <button type="button" className="toast-dismiss"
                  aria-label="dismiss"
                  onClick={() => onDismiss(i)}>×</button>
        </div>
      ))}
    </div>
  );
}

function PendingHoldingScreen({ session, humans, onLogout }) {
  return (
    <main className="pending-screen">
      <h1>Waiting for approval</h1>
      <p className="dim">
        The facilitator has been notified. You'll enter the session once they approve.
      </p>
      <section className="panel">
        <h2>Session: {session?.name || "…"}</h2>
        <h3>Humans in the room</h3>
        {humans.length === 0
          ? <p className="dim">No one yet.</p>
          : <ul className="human-list">{humans.map((h) => (
              <li key={h.id}>
                <strong>{h.display_name}</strong>
                <span className="dim"> ({h.role})</span>
              </li>
            ))}</ul>}
      </section>
      <button type="button" onClick={onLogout}>Cancel and sign out</button>
    </main>
  );
}

function _participantBuckets(participants) {
  // Split into active / paused / pending / departed (offline/removed/
  // reset) / other. Departed get their own bucket so the UI can render
  // them collapsed by default — operators don't want a removed AI's
  // card sitting in the active list with stale management buttons.
  const active = [], paused = [], pending = [], departed = [], other = [];
  for (const p of participants) {
    if (p.role === "pending" || p.status === "pending") pending.push(p);
    else if (p.status === "paused") paused.push(p);
    else if (p.status === "active") active.push(p);
    else if (p.status === "offline" || p.status === "removed" || p.status === "reset") {
      departed.push(p);
    }
    else other.push(p);
  }
  const alpha = (a, b) => a.display_name.localeCompare(b.display_name);
  return {
    active: active.sort(alpha),
    paused: paused.sort(alpha),
    pending: pending.sort(alpha),
    departed: departed.sort(alpha),
    other: other.sort(alpha),
  };
}

function ParticipantList({
  participants, me, skipReasons, isFacilitator, exitRequests,
  onRemove, onRoutingChange, onResetAI, onReleaseAI, onHonorExit, onDismissExit,
}) {
  const byId = useMemo(
    () => Object.fromEntries(participants.map((p) => [p.id, p])),
    [participants],
  );
  const buckets = useMemo(() => _participantBuckets(participants), [participants]);
  const renderCard = (p) => (
    <ParticipantCard key={p.id} p={p} me={me} byId={byId} skipReasons={skipReasons}
      isFacilitator={isFacilitator} onRemove={onRemove} onRoutingChange={onRoutingChange}
      onResetAI={onResetAI} onReleaseAI={onReleaseAI}
      exitRequest={exitRequests?.[p.id]}
      onHonorExit={onHonorExit} onDismissExit={onDismissExit} />
  );
  return (
    <section className="panel participant-list">
      <h2>Participants</h2>
      {participants.length === 0 && <p className="dim">none</p>}
      {buckets.active.length > 0 && (<>
        <h3 className="bucket-label">Active</h3>
        {buckets.active.map(renderCard)}
      </>)}
      {buckets.paused.length > 0 && (<>
        <h3 className="bucket-label">Paused</h3>
        {buckets.paused.map(renderCard)}
      </>)}
      {buckets.pending.length > 0 && (<>
        <h3 className="bucket-label">Pending</h3>
        {buckets.pending.map(renderCard)}
      </>)}
      {buckets.departed.length > 0 && (
        <details className="departed-section">
          <summary>Departed ({buckets.departed.length})</summary>
          {buckets.departed.map(renderCard)}
        </details>
      )}
      {buckets.other.length > 0 && buckets.other.map(renderCard)}
    </section>
  );
}

function ParticipantCard({
  p, me, byId, skipReasons, isFacilitator,
  onRemove, onRoutingChange, onResetAI, onReleaseAI,
  exitRequest, onHonorExit, onDismissExit,
}) {
  const inviter = p.invited_by ? byId[p.invited_by] : null;
  const inviterLabel = inviter ? inviter.display_name : null;
  const isAI = p.provider !== "human";
  const isSelf = p.id === me?.participant_id;
  const isMyAI = isAI && p.invited_by === me?.participant_id;
  // 'reset' joins offline/removed as a "this slot is parked" state — the
  // credentials have been unbound so no management action applies; the
  // facilitator's path forward is Add Participant with the same name.
  const isDeparted = p.status === "offline" || p.status === "removed" || p.status === "reset";
  // Facilitator can manage anyone non-self; a human sponsor can manage
  // AIs they invited (routing + remove + budget + reset). Covers the
  // Test06-Web03 "non-facilitator can't change their sponsored AI's
  // routing/budget" reports. Departed participants can't be re-managed
  // — hides action buttons on already-parked rows so rapid clicks don't
  // produce the Test07-Web08 pattern (cascade-removed AI still visibly
  // clickable).
  const canManage = !isDeparted
    && ((isFacilitator && !isSelf && p.role !== "facilitator") || isMyAI);
  const canResetOrRelease = canManage && isAI;
  return (
    <div className={`participant-card role-${p.role} status-${p.status}`}>
      <div className="p-row">
        <strong>{p.display_name}</strong>
        {isSelf && <span className="badge badge-you">you</span>}
        {(p.role === "pending" || p.status === "pending") && (
          <span className="badge badge-pending">pending</span>
        )}
        {p.status === "reset" && (
          <span className="badge badge-reset" title="API key unbound; slot reservable">
            released
          </span>
        )}
        {canResetOrRelease && onResetAI && (
          <button type="button" className="icon-btn"
            onClick={() => onResetAI(p)}
            title="reset credentials (rotate API key)">↻</button>
        )}
        {canResetOrRelease && onReleaseAI && (
          <button type="button" className="icon-btn"
            onClick={() => onReleaseAI(p)}
            title="release slot (free the display name for re-add)">⏏</button>
        )}
        {canManage && (
          <button type="button" className="icon-btn danger-btn"
            onClick={() => onRemove?.(p)}
            title="remove from session">✕</button>
        )}
      </div>
      <div className="p-meta">
        <span>{p.role}</span>
        <span>·</span>
        <span>{p.provider}</span>
        {p.model_family && <><span>·</span><span>{p.model_family}</span></>}
      </div>
      {isAI && inviterLabel && (
        <div className="p-meta dim">
          <span>added by {inviterLabel}</span>
        </div>
      )}
      {exitRequest && (
        <div className="p-exit-banner" title={`Detected at turn ${exitRequest.turn_number}`}>
          <span className="dim">wants to exit:</span> "{exitRequest.phrase}"
          {isFacilitator && (
            <span className="exit-actions">
              <button type="button" className="small"
                onClick={() => onHonorExit?.(p)}>Honor (→ observer)</button>
              <button type="button" className="small"
                onClick={() => onDismissExit?.(p.id)}>Dismiss</button>
            </span>
          )}
        </div>
      )}
      <div className="p-meta">
        <HealthBadge participant={p} skipReasons={skipReasons?.[p.id]} />
        {isAI && canManage && onRoutingChange ? (
          <select
            className="routing-inline"
            value={p.routing_preference}
            onChange={(ev) => onRoutingChange(p.id, ev.target.value)}
            title="routing preference"
          >
            {ROUTING_PREFERENCES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        ) : isAI ? (
          <span className="routing">{p.routing_preference}</span>
        ) : null}
      </div>
    </div>
  );
}

function SelfControls({ me, participants, isFacilitator, onRoutingChange }) {
  // US2 T071–T072: display the caller's own routing preference. Today the
  // backend's set_routing_preference is facilitator-scoped (PR #61); only
  // facilitators get a live selector. Non-facilitators see read-only with
  // a note pointing at T250 (self-serve endpoint).
  const self = useMemo(
    () => participants.find((p) => p.id === me?.participant_id),
    [participants, me?.participant_id],
  );
  if (!self) return null;

  const spend = self.cost_per_input_token ?? null; // budget bar requires Phase 2b spend map
  const utilLabel = self.budget_daily
    ? `$${fmtDollars(spend || 0)} / $${fmtDollars(self.budget_daily)}`
    : "no daily cap";

  return (
    <section className="panel self-controls">
      <h2>You</h2>
      <div className="kv"><span className="dim">name</span><span>{self.display_name}</span></div>
      <div className="kv"><span className="dim">role</span><span>{self.role}</span></div>
      <div className="kv"><span className="dim">provider</span><span>{self.provider}</span></div>
      <div className="kv"><span className="dim">model</span><span>{self.model || "—"}</span></div>
      <div className="kv"><span className="dim">tier</span><span>{self.model_tier}</span></div>
      <div className="kv"><span className="dim">budget</span><span>{utilLabel}</span></div>
      {self.provider !== "human" && (
        <div className="kv">
          <span className="dim">routing</span>
          <select
            value={self.routing_preference}
            onChange={(ev) => onRoutingChange(self.id, ev.target.value)}
          >
            {ROUTING_PREFERENCES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      )}
    </section>
  );
}

function Transcript({ messages, participants }) {
  const byId = useMemo(
    () => Object.fromEntries(participants.map((p) => [p.id, p])),
    [participants],
  );
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);
  return (
    <section className="transcript">
      {messages.length === 0 && <p className="dim">No messages yet.</p>}
      {messages.map((m) => {
        const speaker = byId[m.speaker_id];
        const html = renderMarkdown(m.content || "");
        const hiddenCount = countInvisibles(m.content || "");
        // For speaker_type="system" the row isn't FROM a participant — it's
        // an automated lifecycle notice (departure, etc.). Use a generic
        // label so the facilitator's name doesn't appear as the speaker.
        const speakerLabel = m.speaker_type === "system"
          ? "System"
          : (speaker?.display_name || m.speaker_id);
        return (
          <article
            key={`${m.turn_number}-${m.speaker_id}`}
            className={`msg msg-${m.speaker_type}`}
          >
            <header>
              <strong>{speakerLabel}</strong>
              <span className="msg-type">{m.speaker_type}</span>
              {hiddenCount > 0 && (
                <span
                  className="invisible-count"
                  title={`${hiddenCount} invisible character(s) unveiled`}
                >
                  ⚠ {hiddenCount} hidden
                </span>
              )}
              <span className="turn-num">#{m.turn_number}</span>
            </header>
            <div className="msg-body" dangerouslySetInnerHTML={{ __html: html }} />
          </article>
        );
      })}
      <div ref={endRef} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Phase 2b dashboards: helpers + new panels
// ---------------------------------------------------------------------------

function deriveHealth(p) {
  // US10 T140: derive a single health state from the participant row.
  if (!p) return { label: "unknown", tone: "dim" };
  const t = p.consecutive_timeouts || 0;
  if (p.status === "paused" && t >= 3) return { label: "breaker-tripped", tone: "danger", count: t };
  if (p.status === "paused") return { label: "paused", tone: "warn" };
  if (p.status === "offline") return { label: "offline", tone: "dim" };
  if (p.status === "pending") return { label: "pending", tone: "dim" };
  if (t > 0) return { label: `warning (${t})`, tone: "warn" };
  return { label: "healthy", tone: "ok" };
}

function HealthBadge({ participant, skipReasons }) {
  const health = deriveHealth(participant);
  const label = health.count != null ? `${health.label} (${health.count})` : health.label;
  const title = skipReasons && skipReasons.length > 0
    ? skipReasons.map((s) => `#${s.turn_number}: ${s.reason}`).join("\n")
    : label;
  return (
    <span className={`health-badge health-${health.tone}`} title={title}>
      {label}
    </span>
  );
}

function pctColor(pct) {
  if (pct >= 0.95) return "var(--danger)";
  if (pct >= 0.50) return "var(--warning)";
  return "var(--ok)";
}

function BudgetPanel({ participants, me, isFacilitator, onSetBudget }) {
  const ais = useMemo(
    () => participants
      .filter((p) => p.provider !== "human")
      .sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [participants],
  );
  const isDeparted = (p) => ["offline", "removed", "reset"].includes(p.status);
  const active = ais.filter((p) => !isDeparted(p));
  const departed = ais.filter(isDeparted);
  if (ais.length === 0) {
    return (
      <section className="panel budget-panel">
        <h2>Budget</h2>
        <p className="dim">No AI participants yet.</p>
      </section>
    );
  }
  const renderCard = (p) => (
    <BudgetCard key={p.id} p={p} me={me}
      isFacilitator={isFacilitator} onSetBudget={onSetBudget} />
  );
  return (
    <section className="panel budget-panel">
      <h2>Budget</h2>
      {active.map(renderCard)}
      {departed.length > 0 && (
        <details className="departed-section">
          <summary>Departed ({departed.length})</summary>
          {departed.map(renderCard)}
        </details>
      )}
    </section>
  );
}

function BudgetCard({ p, me, isFacilitator, onSetBudget }) {
  const isSelf = p.id === me?.participant_id;
  const isMyAI = p.provider !== "human" && p.invited_by === me?.participant_id;
  // 'reset' / 'offline' / 'removed' are departed states — credentials
  // are unbound or the row is closed, so editing budget is meaningless
  // (and was confusing in shakedown — operators saw an edit button on
  // a removed AI). Match the ParticipantCard isDeparted gate.
  const isDeparted = p.status === "offline" || p.status === "removed" || p.status === "reset";
  // Facilitator sees everything; self sees own; sponsor sees $ on AIs
  // they invited. Others still only see utilization % (US4 privacy).
  const showDollars = isFacilitator || isSelf || isMyAI;
  const canEdit = !isDeparted && (isFacilitator || isMyAI);
  const [editing, setEditing] = useState(false);
  const { cap, spend, label } = _activeBudget(p);
  const utilization = cap ? Math.min(1, spend / cap) : null;
  const maxTok = p.max_tokens_per_turn;
  return (
    <div className="budget-card">
      <div className="p-row">
        <strong>{p.display_name}</strong>
        {showDollars && (
          <span className="dim">
            ${fmtDollars(spend)}{cap ? ` / $${fmtDollars(cap)} (${label})` : " (no cap)"}
            {maxTok ? ` · max ${maxTok} tok/turn` : ""}
          </span>
        )}
        {canEdit && !editing && (
          <button type="button" className="link-btn" onClick={() => setEditing(true)}>
            edit
          </button>
        )}
      </div>
      {utilization !== null && (
        <div className="util-bar">
          <div className="util-fill"
            style={{ width: `${Math.round(utilization * 100)}%`, background: pctColor(utilization) }} />
          {!showDollars && <span className="util-pct">{Math.round(utilization * 100)}%</span>}
        </div>
      )}
      {editing && (
        <BudgetEditor p={p} onSave={onSetBudget} onClose={() => setEditing(false)} />
      )}
    </div>
  );
}

function _activeBudget(p) {
  // Prefer daily when both are set (longer window gives more useful context).
  // Falls back to hourly when only hourly is configured — previously the UI
  // mis-labeled hourly-only budgets as "no cap" (Test06-Web06).
  if (p.budget_daily != null) {
    return { cap: p.budget_daily, spend: p.spend_daily ?? 0, label: "daily" };
  }
  if (p.budget_hourly != null) {
    return { cap: p.budget_hourly, spend: p.spend_hourly ?? 0, label: "hourly" };
  }
  return { cap: null, spend: p.spend_daily ?? 0, label: "" };
}

function BudgetEditor({ p, onSave, onClose }) {
  const [hourly, setHourly] = useState(p.budget_hourly ?? "");
  const [daily, setDaily] = useState(p.budget_daily ?? "");
  const [maxTok, setMaxTok] = useState(p.max_tokens_per_turn ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const parseMoney = (s) => {
    if (s === "" || s == null) return null;
    const n = parseFloat(s);
    return Number.isFinite(n) && n >= 0 ? n : "invalid";
  };
  const parseTok = (s) => {
    if (s === "" || s == null) return null;
    const n = parseInt(s, 10);
    return Number.isFinite(n) && n > 0 ? n : "invalid";
  };
  const save = async (payload) => {
    setBusy(true); setError(null);
    try {
      await onSave(p.id, payload);
      onClose();
    } catch (e) { setError(e.message || "Save failed"); }
    finally { setBusy(false); }
  };
  const submit = async (ev) => {
    ev.preventDefault();
    const h = parseMoney(hourly); const d = parseMoney(daily); const t = parseTok(maxTok);
    if (h === "invalid" || d === "invalid") { setError("Budgets must be >= 0"); return; }
    if (t === "invalid") { setError("Max tokens must be a positive integer"); return; }
    await save({ budget_hourly: h, budget_daily: d, max_tokens_per_turn: t });
  };
  const clearCaps = () => {
    setHourly(""); setDaily(""); setMaxTok("");
    save({ budget_hourly: null, budget_daily: null, max_tokens_per_turn: null });
  };
  return (
    <form onSubmit={submit} className="budget-editor">
      <label>hourly $ <input type="number" step="0.01" min="0" value={hourly}
        onChange={(ev) => setHourly(ev.target.value)} placeholder="no cap" /></label>
      <label>daily $ <input type="number" step="0.01" min="0" value={daily}
        onChange={(ev) => setDaily(ev.target.value)} placeholder="no cap" /></label>
      <label>max tok <input type="number" step="1" min="1" value={maxTok}
        onChange={(ev) => setMaxTok(ev.target.value)} placeholder="no limit" /></label>
      {error && <div className="error">{error}</div>}
      <div className="budget-editor-actions">
        <button type="button" onClick={onClose}>cancel</button>
        <button type="button" onClick={clearCaps} disabled={busy}
          title="Remove all caps (no spending or token limits)">
          no cap
        </button>
        <button type="submit" className={busy ? "busy" : ""} disabled={busy}>
          {busy ? "saving" : "save"}
        </button>
      </div>
    </form>
  );
}

function ConvergencePanel({ scores, threshold = 0.85 }) {
  // US4 T101. Inline SVG sparkline of last 50 scores + threshold line.
  const points = scores.slice(-50);
  if (points.length < 2) {
    return (
      <section className="panel">
        <h2>Convergence</h2>
        <p className="dim">Waiting for data (≥2 turns needed).</p>
      </section>
    );
  }
  const w = 240;
  const h = 60;
  const xs = points.map((_, i) => (i / (points.length - 1)) * w);
  const ys = points.map((pt) => h - Math.max(0, Math.min(1, pt.similarity_score || 0)) * h);
  const pathD = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const lastScore = points[points.length - 1].similarity_score;
  const thresholdY = h - threshold * h;
  return (
    <section className="panel convergence-panel">
      <h2>Convergence</h2>
      <svg viewBox={`0 0 ${w} ${h}`} className="sparkline" role="img" aria-label="convergence sparkline">
        <line
          x1="0" y1={thresholdY} x2={w} y2={thresholdY}
          stroke="var(--warning)" strokeDasharray="3,3" strokeWidth="1"
        />
        <path d={pathD} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        {points.map((pt, i) => pt.divergence_prompted && (
          <circle key={i} cx={xs[i]} cy={ys[i]} r="2.5" fill="var(--danger)" />
        ))}
      </svg>
      <div className="kv">
        <span className="dim">last</span>
        <span>{typeof lastScore === "number" ? lastScore.toFixed(3) : "—"}</span>
      </div>
      <div className="kv">
        <span className="dim">threshold</span>
        <span>{threshold.toFixed(2)}</span>
      </div>
    </section>
  );
}

function SummaryPanel({ summary, onLoadHistory, onLoadReviewGates, onExport }) {
  // US9 T130–T133. Latest summary at top, plus two collapsed details blocks
  // for earlier summary checkpoints and review-gate history. Both refetch on
  // every open click — the original first-fetch-only cache went stale as
  // soon as a new summary or review-gate event landed.
  const [open, setOpen] = useState(true);
  const [history, setHistory] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [gates, setGates] = useState(null);
  const [gatesOpen, setGatesOpen] = useState(false);
  const [gatesBusy, setGatesBusy] = useState(false);

  if (!summary) {
    return (
      <section className="panel">
        <h2>Summary</h2>
        <p className="dim">No checkpoint yet — summaries run every 10 turns.</p>
      </section>
    );
  }

  const toggleHistory = async () => {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (!next || !onLoadHistory) return;
    setHistoryBusy(true);
    try {
      const rows = await onLoadHistory();
      setHistory(rows || []);
    } catch (e) {
      setHistory([]);
      alert(`Load history failed: ${e.message}`);
    } finally {
      setHistoryBusy(false);
    }
  };

  const toggleGates = async () => {
    const next = !gatesOpen;
    setGatesOpen(next);
    if (!next || !onLoadReviewGates) return;
    setGatesBusy(true);
    try {
      const rows = await onLoadReviewGates();
      setGates(rows || []);
    } catch (e) {
      setGates([]);
      alert(`Load review gates failed: ${e.message}`);
    } finally {
      setGatesBusy(false);
    }
  };

  const handleExport = async (fmt) => {
    if (!onExport) return;
    try {
      const result = await onExport(fmt);
      _downloadBlob(
        result.content,
        fmt === "markdown" ? "text/markdown" : "application/json",
        `sacp-summaries.${fmt === "markdown" ? "md" : "json"}`,
      );
    } catch (e) {
      alert(`Export failed: ${e.message}`);
    }
  };

  return (
    <section className="panel summary-panel">
      <div className="panel-header" onClick={() => setOpen(!open)}>
        <h2>Summary (turn {summary.turn_number})</h2>
        <span className="toggle">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <>
          <SummaryBody summary={summary} />
          <div className="summary-actions">
            <button type="button" className="small"
              onClick={(ev) => { ev.stopPropagation(); handleExport("markdown"); }}>
              Export .md
            </button>
            <button type="button" className="small"
              onClick={(ev) => { ev.stopPropagation(); handleExport("json"); }}>
              Export .json
            </button>
          </div>
          <details className="summary-history" open={historyOpen}>
            <summary onClick={(ev) => { ev.preventDefault(); toggleHistory(); }}>
              Earlier checkpoints {history ? `(${Math.max(0, history.length - 1)})` : ""}
            </summary>
            {historyBusy && <p className="dim">Loading…</p>}
            {history && history.length <= 1 && !historyBusy && (
              <p className="dim">No earlier checkpoints.</p>
            )}
            {history && history.length > 1 && history.slice(0, -1).reverse().map((row) => (
              <div key={row.turn_number} className="summary-history-entry">
                <h4>Turn {row.turn_number}</h4>
                <SummaryBody summary={row.summary} />
              </div>
            ))}
          </details>
          <details className="summary-history" open={gatesOpen}>
            <summary onClick={(ev) => { ev.preventDefault(); toggleGates(); }}>
              Review gate history {gates ? `(${gates.length})` : ""}
            </summary>
            {gatesBusy && <p className="dim">Loading…</p>}
            {gates && gates.length === 0 && !gatesBusy && (
              <p className="dim">No review-gate events yet.</p>
            )}
            {gates && gates.length > 0 && gates.map((g) => (
              <div key={`${g.timestamp}-${g.draft_id}`} className="gate-history-entry">
                <span className={`pill pill-${g.action.replace("review_gate_", "")}`}>
                  {g.action.replace("review_gate_", "")}
                </span>
                <span className="dim"> draft {g.draft_id?.slice(0, 8)}</span>
                {g.reason && <div className="gate-reason">{g.reason}</div>}
                <div className="dim small">{g.timestamp}</div>
              </div>
            ))}
          </details>
        </>
      )}
    </section>
  );
}

function SummaryBody({ summary }) {
  // Shared renderer for the latest summary + each historical checkpoint.
  const { decisions = [], open_questions = [], key_positions = [], narrative } = summary || {};
  return (
    <>
      {narrative && <p className="narrative">{narrative}</p>}
      {decisions.length > 0 && (
        <div>
          <h3>Decisions</h3>
          <ul>{decisions.map((d, i) => (
            <li key={i}><span className={`pill pill-${d.status}`}>{d.status}</span> {d.summary}</li>
          ))}</ul>
        </div>
      )}
      {open_questions.length > 0 && (
        <div>
          <h3>Open questions</h3>
          <ul>{open_questions.map((q, i) => <li key={i}>{q.summary}</li>)}</ul>
        </div>
      )}
      {key_positions.length > 0 && (
        <div>
          <h3>Positions</h3>
          <ul>{key_positions.map((k, i) => (
            <li key={i}><strong>{k.participant}:</strong> {k.position}</li>
          ))}</ul>
        </div>
      )}
    </>
  );
}

function _downloadBlob(content, mimeType, filename) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function DraftCard({ draft, speaker, isFacilitator, onApprove, onReject, onEdit }) {
  const [needsOverride, setNeedsOverride] = useState(false);
  const [overrideText, setOverrideText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const preview = (draft.draft_content || "").slice(0, 240);

  const handleApprove = async (overrideReason) => {
    setBusy(true);
    setError(null);
    try {
      await onApprove(draft.id, overrideReason || undefined);
      setNeedsOverride(false);
    } catch (e) {
      if (e.message.startsWith("422")) {
        setNeedsOverride(true);
        setError("Security pipeline re-flagged this draft. Provide a justification to override.");
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="draft-card">
      <header>
        <strong>{speaker?.display_name || draft.participant_id}</strong>
        <span className="dim">{draft.created_at ? new Date(draft.created_at).toLocaleTimeString() : ""}</span>
      </header>
      <div className="draft-body">
        <pre>{preview}{draft.draft_content.length > 240 ? "…" : ""}</pre>
      </div>
      {error && <div className="error">{error}</div>}
      {isFacilitator && !needsOverride && (
        <div className="draft-actions">
          <button onClick={() => handleApprove()} disabled={busy}>Approve</button>
          <button onClick={() => onEdit(draft)} disabled={busy}>Edit</button>
          <button onClick={() => onReject(draft.id)} disabled={busy} className="danger">Reject</button>
        </div>
      )}
      {isFacilitator && needsOverride && (
        <div className="override-reason-form">
          <label>
            Override justification (required):
            <textarea
              rows={3}
              maxLength={1024}
              value={overrideText}
              onChange={(ev) => setOverrideText(ev.target.value)}
              disabled={busy}
              placeholder="State why this flagged content should be approved..."
            />
          </label>
          <div className="draft-actions">
            <button
              onClick={() => handleApprove(overrideText)}
              disabled={busy || !overrideText.trim()}
            >
              {busy ? "Submitting…" : "Approve with justification"}
            </button>
            <button type="button" onClick={() => { setNeedsOverride(false); setError(null); }} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewGateQueue({ drafts, participants, pauseScope, isFacilitator, onApprove, onReject, onEdit, onToggleScope }) {
  // US5 T110–T114.
  const byId = useMemo(
    () => Object.fromEntries(participants.map((p) => [p.id, p])),
    [participants],
  );
  return (
    <section className="panel review-gate-panel">
      <div className="panel-header">
        <h2>Review gate</h2>
        {isFacilitator && (
          <select
            value={pauseScope || "session"}
            onChange={(ev) => onToggleScope(ev.target.value)}
            title="Pause scope"
          >
            <option value="session">session-wide pause</option>
            <option value="participant">participant-only pause</option>
          </select>
        )}
      </div>
      {drafts.length === 0 && <p className="dim">No pending drafts.</p>}
      {drafts.map((d) => (
        <DraftCard
          key={d.id}
          draft={d}
          speaker={byId[d.participant_id]}
          isFacilitator={isFacilitator}
          onApprove={onApprove}
          onReject={onReject}
          onEdit={onEdit}
        />
      ))}
    </section>
  );
}

const MAX_EDIT_CHARS = 8_000; // mirrors server-side _MAX_FACILITATOR_EDIT_CHARS

function ReviewGateEditor({ draft, onSave, onClose }) {
  const [text, setText] = useState(draft.draft_content);
  const [overrideText, setOverrideText] = useState("");
  const [needsOverride, setNeedsOverride] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const remaining = MAX_EDIT_CHARS - text.length;
  const counterClass = remaining <= 100 ? "char-counter danger"
    : remaining <= 500 ? "char-counter warn"
    : "char-counter dim";
  const atLimit = text.length > MAX_EDIT_CHARS;

  const submit = async (overrideReason) => {
    if (!text.trim() || atLimit) return;
    setBusy(true);
    setError(null);
    try {
      await onSave(draft.id, text, overrideReason || undefined);
      onClose();
    } catch (e) {
      if (e.message.startsWith("422")) {
        setNeedsOverride(true);
        setError("Edited content still re-flags the pipeline. Provide a justification to override.");
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={(ev) => ev.stopPropagation()}>
        <h2>Edit draft</h2>
        <textarea
          rows={14}
          value={text}
          onChange={(ev) => { setText(ev.target.value); setNeedsOverride(false); }}
          disabled={busy}
          maxLength={MAX_EDIT_CHARS}
        />
        {error && <div className="error">{error}</div>}
        {needsOverride && (
          <div className="override-reason-form">
            <label>
              Override justification (required):
              <textarea
                rows={3}
                maxLength={1024}
                value={overrideText}
                onChange={(ev) => setOverrideText(ev.target.value)}
                disabled={busy}
                placeholder="State why this flagged content should be approved..."
              />
            </label>
          </div>
        )}
        <div className="modal-actions">
          <span className={counterClass}>{remaining.toLocaleString()} / {MAX_EDIT_CHARS.toLocaleString()}</span>
          <button type="button" onClick={onClose}>Cancel</button>
          <button
            onClick={() => submit(needsOverride ? overrideText : undefined)}
            disabled={busy || !text.trim() || atLimit || (needsOverride && !overrideText.trim())}
          >
            {busy ? "Saving…" : "Save + approve"}
          </button>
        </div>
      </div>
    </div>
  );
}

function AdminPanel({ participants, session, auditEntries, onApprove, onReject, onInvite, onTransfer, onConfig }) {
  // US6 T120–T125.
  const [open, setOpen] = useState(false);
  const [invite, setInvite] = useState(null);
  const [maxUses, setMaxUses] = useState(1);

  const pending = useMemo(
    () => participants.filter((p) => p.role === "pending" || p.status === "pending"),
    [participants],
  );
  const activeOthers = useMemo(
    () => participants.filter((p) => p.status === "active" && p.role !== "facilitator"),
    [participants],
  );

  const createInvite = async () => {
    try {
      const result = await onInvite(maxUses);
      setInvite(result);
    } catch (e) {
      alert(`Invite failed: ${e.message}`);
    }
  };

  const copy = (text) => navigator.clipboard?.writeText(text);

  return (
    <section className="panel admin-panel">
      <div className="panel-header" onClick={() => setOpen(!open)}>
        <h2>Admin</h2>
        <span className="toggle">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <>
          <details open={pending.length > 0}>
            <summary>Pending approvals ({pending.length})</summary>
            {pending.length === 0 && <p className="dim">None.</p>}
            {pending.map((p) => (
              <div key={p.id} className="pending-row">
                <span>{p.display_name}</span>
                <div className="button-row">
                  <button onClick={() => onApprove(p.id)}>Approve</button>
                  <button onClick={() => onReject(p.id)} className="danger">Reject</button>
                </div>
              </div>
            ))}
          </details>
          <details>
            <summary>Invite</summary>
            <div className="kv">
              <span className="dim">max uses</span>
              <input
                type="number"
                min="1"
                max="20"
                value={maxUses}
                onChange={(ev) => setMaxUses(parseInt(ev.target.value, 10) || 1)}
              />
            </div>
            <button onClick={createInvite}>Generate invite</button>
            {invite && (
              <div className="invite-display">
                <CopyableToken token={invite.invite_token} />
                <p className="dim">Share this code. Recipient uses "Redeem an invite code" on the landing page.</p>
              </div>
            )}
          </details>
          <details>
            <summary>Session config</summary>
            <div className="kv">
              <span className="dim">cadence</span>
              <select
                value={session?.cadence_preset || "cruise"}
                onChange={(ev) => onConfig("cadence_preset", { preset: ev.target.value })}
              >
                <option>sprint</option><option>cruise</option><option>idle</option>
              </select>
            </div>
            <div className="kv">
              <span className="dim">acceptance</span>
              <select
                value={session?.acceptance_mode || "unanimous"}
                onChange={(ev) => onConfig("acceptance_mode", { mode: ev.target.value })}
              >
                <option>unanimous</option><option>majority</option>
              </select>
            </div>
            <div className="kv">
              <span className="dim">min tier</span>
              <select
                value={session?.min_model_tier || "low"}
                onChange={(ev) => onConfig("min_model_tier", { tier: ev.target.value })}
              >
                <option>low</option><option>mid</option><option>high</option><option>max</option>
              </select>
            </div>
            <div className="kv">
              <span className="dim">classifier</span>
              <select
                value={session?.complexity_classifier_mode || "pattern"}
                onChange={(ev) => onConfig("complexity_classifier_mode", { mode: ev.target.value })}
              >
                <option>pattern</option><option>llm</option>
              </select>
            </div>
          </details>
          <details>
            <summary>Transfer facilitator</summary>
            {activeOthers.length === 0 && <p className="dim">No eligible targets.</p>}
            {activeOthers.map((p) => (
              <div key={p.id} className="pending-row">
                <span>{p.display_name}</span>
                <button onClick={() => {
                  if (confirm(`Transfer facilitator to ${p.display_name}?`)) onTransfer(p.id);
                }}>Transfer</button>
              </div>
            ))}
          </details>
          <details>
            <summary>Audit log (last {auditEntries.length})</summary>
            {auditEntries.length === 0 && <p className="dim">No entries yet.</p>}
            {auditEntries.slice(0, 20).map((e) => (
              <div key={e.id} className="audit-row">
                <span className="dim">{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ""}</span>
                <span className="audit-action">{e.action}</span>
                <span className="dim">→</span>
                <code>{e.target_id}</code>
              </div>
            ))}
          </details>
        </>
      )}
    </section>
  );
}

function AIQuestionsPanel({ questions, participants, onResolve }) {
  // Surfaces AI-emitted questions that the heuristic detector flagged
  // as plausibly aimed at a participant. Transient (not persisted on
  // the server) — ephemeral signal that "this question is sitting
  // unanswered" so humans don't lose direct prompts under fast turns.
  if (!questions || questions.length === 0) return null;
  const nameOf = (pid) => {
    const p = participants.find((x) => x.id === pid);
    return p ? p.display_name : pid;
  };
  return (
    <section className="panel ai-questions-panel">
      <h2>Open AI questions ({questions.length})</h2>
      <ul className="ai-questions-list">
        {questions.map((q) => (
          <li key={q.key}>
            <div className="q-meta">
              <strong>{nameOf(q.participant_id)}</strong>
              <span className="dim"> · turn {q.turn_number}</span>
              <button type="button" className="small"
                onClick={() => onResolve?.(q.key)}
                title="dismiss this question">✓</button>
            </div>
            <div className="q-body">{q.question}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ProposalTracker({ proposals, resolved, me, isFacilitator, onCreate, onVote, onResolve }) {
  // US7 T151–T153 + resolved-history (Test06 feedback).
  const [showCreator, setShowCreator] = useState(false);
  const [myVotes, setMyVotes] = useState({});

  const recordVote = (pid) => setMyVotes((prev) => ({ ...prev, [pid]: true }));

  return (
    <section className="panel proposal-panel">
      <div className="panel-header">
        <h2>Proposals</h2>
        <button onClick={() => setShowCreator(true)}>+ New</button>
      </div>
      {proposals.length === 0 && <p className="dim">No open proposals.</p>}
      {proposals.map((p) => {
        const tally = p.tally || { accept: 0, reject: 0, abstain: 0 };
        const alreadyVoted = myVotes[p.id] === true;
        return (
          <div key={p.id} className="proposal-card">
            <header>
              <strong>{p.topic}</strong>
              <span className="dim">{p.acceptance_mode}</span>
            </header>
            <p className="proposal-position">{p.position}</p>
            <div className="tally">
              <span className="pill pill-accepted">✓ {tally.accept}</span>
              <span className="pill pill-rejected">✗ {tally.reject}</span>
              <span className="pill pill-pending">· {tally.abstain}</span>
            </div>
            <div className="button-row">
              <button
                disabled={alreadyVoted}
                onClick={async () => {
                  try { await onVote(p.id, "accept"); recordVote(p.id); }
                  catch (e) { alert(e.message); }
                }}
              >Accept</button>
              <button
                disabled={alreadyVoted}
                onClick={async () => {
                  try { await onVote(p.id, "reject"); recordVote(p.id); }
                  catch (e) { alert(e.message); }
                }}
              >Reject</button>
              <button
                disabled={alreadyVoted}
                onClick={async () => {
                  try { await onVote(p.id, "abstain"); recordVote(p.id); }
                  catch (e) { alert(e.message); }
                }}
              >Abstain</button>
            </div>
            {isFacilitator && (
              <div className="button-row">
                <button onClick={() => onResolve(p.id, "accepted")} className="resolve-accept">
                  Resolve: accept
                </button>
                <button onClick={() => onResolve(p.id, "rejected")} className="danger">
                  Resolve: reject
                </button>
              </div>
            )}
          </div>
        );
      })}
      {resolved && resolved.length > 0 && (
        <details className="resolved-proposals">
          <summary>Resolved ({resolved.length})</summary>
          {resolved.map((p) => {
            const tally = p.tally || { accept: 0, reject: 0, abstain: 0 };
            return (
              <div key={p.id} className="proposal-card resolved">
                <header>
                  <strong>{p.topic}</strong>
                  <span className={`pill pill-${p.status}`}>{p.status}</span>
                </header>
                <p className="proposal-position dim">{p.position}</p>
                <div className="tally">
                  <span className="pill pill-accepted">✓ {tally.accept}</span>
                  <span className="pill pill-rejected">✗ {tally.reject}</span>
                  <span className="pill pill-pending">· {tally.abstain}</span>
                </div>
              </div>
            );
          })}
        </details>
      )}
      {showCreator && (
        <ProposalCreator
          onClose={() => setShowCreator(false)}
          onCreate={async (topic, position) => {
            await onCreate(topic, position);
            setShowCreator(false);
          }}
        />
      )}
    </section>
  );
}

function ProposalCreator({ onClose, onCreate }) {
  const [topic, setTopic] = useState("");
  const [position, setPosition] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (ev) => {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onCreate(topic.trim(), position.trim());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(ev) => ev.stopPropagation()}>
        <h2>New proposal</h2>
        <form onSubmit={submit}>
          <label>Topic
            <input value={topic} onChange={(ev) => setTopic(ev.target.value)} required />
          </label>
          <label>Position
            <textarea rows={4} value={position} onChange={(ev) => setPosition(ev.target.value)} required />
          </label>
          {error && <div className="error">{error}</div>}
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" disabled={busy || !topic.trim() || !position.trim()}>
              {busy ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const MAX_MSG_CHARS = 2_000; // mirrors server-side MAX_MESSAGE_CONTENT_CHARS

function MessageInput({ onSend, disabled }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const remaining = MAX_MSG_CHARS - text.length;
  const counterClass = remaining <= 100 ? "char-counter danger"
    : remaining <= 500 ? "char-counter warn"
    : "char-counter dim";
  const atLimit = text.length > MAX_MSG_CHARS;

  const send = async () => {
    const trimmed = text.trim();
    if (!trimmed || busy || atLimit) return;
    setBusy(true);
    try {
      await onSend(trimmed);
      setText("");
    } catch (e) {
      alert(`Send failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (ev) => {
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      send();
    }
  };

  return (
    <div className="message-input">
      <textarea
        value={text}
        onChange={(ev) => setText(ev.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Type a message — Ctrl+Enter to send"
        disabled={disabled || busy}
        maxLength={MAX_MSG_CHARS}
        rows={3}
      />
      <div className="input-actions">
        <span className="dim">Ctrl+Enter to send</span>
        <span className={counterClass}>{remaining.toLocaleString()} / {MAX_MSG_CHARS.toLocaleString()}</span>
        <button onClick={send} className={busy ? "busy" : ""} disabled={disabled || busy || !text.trim() || atLimit}>
          {busy ? "Sending" : "Send"}
        </button>
      </div>
    </div>
  );
}

function SessionControls({ session, isFacilitator, onAction, onSummarize, onReviewGateAll }) {
  if (!isFacilitator) return null;
  const canStart = session?.status === "active";
  const allInGate = session?.all_ais_in_review_gate;
  const [summarizing, setSummarizing] = useState(false);
  const onArchive = () => {
    if (!confirm(
      "Archive this session?\n\n" +
      "The loop will stop, all participants will be notified, " +
      "and a final summary will be generated. This cannot be undone."
    )) return;
    onAction("archive");
  };
  const toggleGate = () => onReviewGateAll(allInGate ? "always" : "review_gate");
  const runSummarize = async () => {
    if (summarizing) return;
    setSummarizing(true);
    try { await onSummarize(); } finally { setSummarizing(false); }
  };
  return (
    <section className="panel session-controls">
      <h2>Session</h2>
      {session?.id && (
        <div className="kv">
          <span className="dim">id</span>
          <code className="session-id" title="session id (shareable)">{session.id}</code>
        </div>
      )}
      <div className="button-row">
        <button onClick={() => onAction("start_loop")} disabled={!canStart}>Start loop</button>
        <button onClick={() => onAction("stop_loop")}>Stop loop</button>
      </div>
      <div className="button-row">
        <button onClick={() => onAction("pause")}>Pause</button>
        <button onClick={() => onAction("resume")}>Resume</button>
      </div>
      <div className="button-row">
        <button onClick={runSummarize} disabled={summarizing}
          title="Force a summary checkpoint now">
          {summarizing ? "Summarizing…" : "Summarize now"}
        </button>
        <button onClick={toggleGate}
          title="Flip every AI between review-gated and always-on routing">
          {allInGate ? "Ungate all AIs" : "Review-gate all AIs"}
        </button>
      </div>
      <div className="button-row">
        <button onClick={onArchive} className="danger">Archive</button>
      </div>
    </section>
  );
}

const PROVIDER_DEFAULTS = {
  human:     { model: "human",                            family: "human",    tier: "n/a", context: 0,     needsKey: false },
  anthropic: { model: "anthropic/claude-haiku-4-5-20251001", family: "claude", tier: "mid", context: 200000, needsKey: true },
  openai:    { model: "gpt-4o-mini",                       family: "gpt",      tier: "mid", context: 128000, needsKey: true },
  ollama:    { model: "ollama_chat/llama3.2:3b",           family: "llama",    tier: "low", context: 4096,   needsKey: false },
  gemini:    { model: "gemini/gemini-2.5-flash-lite",      family: "gemini",   tier: "low", context: 1000000, needsKey: true },
  groq:      { model: "groq/llama-3.3-70b-versatile",      family: "llama",    tier: "mid", context: 128000, needsKey: true },
};

function _applyProviderDefaults(form, provider) {
  const d = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.human;
  return {
    ...form,
    provider,
    model: d.model,
    model_family: d.family,
    model_tier: d.tier,
    context_window: d.context,
  };
}

// Round10 surfaced a participant with provider="anthropic" + model="ollama_chat/...":
// the picker only set `model` and the validator never cross-checked. This helper
// gives both surfaces a single source of truth for "which provider owns this model
// string." Returns null for self-hosted gateway / exotic models so hand-tuned
// strings still work.
function _providerFromModel(model) {
  if (!model) return null;
  if (model.startsWith("anthropic/")) return "anthropic";
  if (model.startsWith("gemini/")) return "gemini";
  if (model.startsWith("groq/")) return "groq";
  if (model.startsWith("ollama_chat/") || model.startsWith("ollama/")) return "ollama";
  if (/^(gpt-|o1-|o3-|chatgpt-)/.test(model)) return "openai";
  return null;
}

// _applyProviderDefaults overwrites model with the provider's default. When the
// picker hands back a specific model whose prefix implies a different provider,
// re-apply provider defaults (so family/tier/context align) and put the picked
// model back. No-op when model already matches the current provider.
function _applyPickedModel(form, model) {
  const derived = _providerFromModel(model);
  if (derived && derived !== form.provider) {
    return { ..._applyProviderDefaults(form, derived), model };
  }
  return { ...form, model };
}

function _validateAddParticipant(form) {
  if (!form.display_name.trim()) return "Display name is required";
  if (form.provider === "human") return null;
  if (!form.model.trim() || form.model.toLowerCase() === "string") {
    return "Model is required for AI participants";
  }
  if (form.model === "human") return "Model cannot be 'human' for an AI participant";
  if (PROVIDER_DEFAULTS[form.provider]?.needsKey && !form.api_key.trim()) {
    return `API key is required for ${form.provider}`;
  }
  const derived = _providerFromModel(form.model);
  if (derived && derived !== form.provider) {
    return `Model "${form.model}" looks like a ${derived} model — switch provider to "${derived}" or pick a different model.`;
  }
  // Round11: Llama 3 was created with the placeholder string itself as the
  // api_endpoint value (operator pasted the hint). Reject anything containing
  // angle brackets — never legitimate in a real URL, always a placeholder leak.
  if (form.api_endpoint && /[<>]/.test(form.api_endpoint)) {
    return `API endpoint "${form.api_endpoint}" contains placeholder characters (< or >) — replace with a real URL.`;
  }
  return null;
}

function AddParticipantDialog({ onClose, onAdd, onFetchModels, aiOnly = false }) {
  const initial = aiOnly
    ? _applyProviderDefaults({ display_name: "", api_key: "", api_endpoint: "" }, "anthropic")
    : { display_name: "", provider: "human", model: "human",
        model_tier: "n/a", model_family: "human", context_window: 0,
        api_key: "", api_endpoint: "" };
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const update = (field) => (ev) => setForm({ ...form, [field]: ev.target.value });
  const pickProvider = (ev) => setForm(_applyProviderDefaults(form, ev.target.value));

  const submit = async (ev) => {
    ev.preventDefault();
    const validationError = _validateAddParticipant(form);
    if (validationError) { setError(validationError); return; }
    setBusy(true); setError(null);
    const tok = parseInt(form.max_tokens_per_turn, 10);
    const parsedTok = Number.isFinite(tok) && tok > 0 ? tok : null;
    try {
      await onAdd({
        ...form,
        context_window: parseInt(form.context_window, 10) || 0,
        max_tokens_per_turn: parsedTok,
      });
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const isAI = form.provider !== "human";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(ev) => ev.stopPropagation()}>
        <h2>{aiOnly ? "Add your AI" : "Add participant"}</h2>
        <form onSubmit={submit}>
          <label>Display name
            <input value={form.display_name} onChange={update("display_name")} required autoFocus />
          </label>
          <label>Provider
            <select value={form.provider} onChange={pickProvider}>
              {!aiOnly && <option value="human">human</option>}
              <option value="anthropic">anthropic</option>
              <option value="openai">openai</option>
              <option value="gemini">gemini</option>
              <option value="groq">groq</option>
              <option value="ollama">ollama</option>
            </select>
          </label>
          {isAI && (
            <>
              <label>Model
                <input value={form.model} onChange={update("model")} required />
              </label>
              <label>Model family
                <input value={form.model_family} onChange={update("model_family")} />
              </label>
              <label>Model tier
                <select value={form.model_tier} onChange={update("model_tier")}>
                  <option>low</option>
                  <option>mid</option>
                  <option>high</option>
                  <option>max</option>
                </select>
              </label>
              <label>Context window
                <input type="number" value={form.context_window} onChange={update("context_window")} />
              </label>
              <label>Max tokens / turn
                <input type="number" step="1" min="1"
                  value={form.max_tokens_per_turn ?? ""}
                  onChange={update("max_tokens_per_turn")}
                  placeholder="no limit" />
              </label>
              {PROVIDER_DEFAULTS[form.provider]?.needsKey && (
                <label>API key
                  <input type="password" value={form.api_key}
                    onChange={update("api_key")} required />
                  {_keyPrefixWarning(form.provider, form.api_key) && (
                    <div className="warn key-warning">
                      {_keyPrefixWarning(form.provider, form.api_key)}
                    </div>
                  )}
                </label>
              )}
              <label>API endpoint (optional, for Ollama/custom)
                <input
                  value={form.api_endpoint || ""}
                  onChange={update("api_endpoint")}
                  placeholder={_endpointPlaceholder(form.provider)}
                />
              </label>
              {_endpointHint(form.provider) && (
                <small className="dim">{_endpointHint(form.provider)}</small>
              )}
              {onFetchModels && (
                <ProviderModelPicker
                  provider={form.provider}
                  apiKey={form.api_key}
                  apiEndpoint={form.api_endpoint || ""}
                  onFetch={onFetchModels}
                  onPick={(picked) => setForm((f) => _applyPickedModel(f, picked))}
                />
              )}
            </>
          )}
          {error && <div className="error">{error}</div>}
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className={busy ? "busy" : ""} disabled={busy}>
              {busy ? "Adding…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Recognized API key prefixes per provider. Used by AddParticipantDialog
// and ResetAICredentialsDialog to warn (not block) when an operator
// pastes a key that doesn't match the selected provider — observed
// during shakedown when an `sk-ant-` key got pasted into an OpenAI
// slot, producing a confusing 401 from the OpenAI endpoint instead of
// an upfront UI signal. Soft warning only — self-hosted gateways +
// custom proxies may use arbitrary tokens, so we don't block submit.
const _PROVIDER_KEY_PREFIXES = {
  openai:    { matches: (k) => k.startsWith("sk-") && !k.startsWith("sk-ant-"),
               hint: "OpenAI keys typically start with `sk-` (and not `sk-ant-`)." },
  anthropic: { matches: (k) => k.startsWith("sk-ant-"),
               hint: "Anthropic keys typically start with `sk-ant-`." },
  gemini:    { matches: (k) => k.startsWith("AIza"),
               hint: "Gemini keys typically start with `AIza`." },
  groq:      { matches: (k) => k.startsWith("gsk_"),
               hint: "Groq keys typically start with `gsk_`." },
};

function _keyPrefixWarning(provider, apiKey) {
  if (!apiKey || !apiKey.trim()) return null;
  const rule = _PROVIDER_KEY_PREFIXES[provider];
  if (!rule) return null;
  if (rule.matches(apiKey.trim())) return null;
  return `Heads up: this doesn't look like a ${provider} key. ${rule.hint}`;
}

// Hint shown under the API endpoint field. Ollama gets a concrete URL
// since "what do I type?" is the most-asked question for that provider
// (Round09 #16); other providers see a generic LiteLLM-proxy example.
// docker-compose.yml maps host.docker.internal:host-gateway so the
// SACP-in-Docker case below resolves cleanly.
function _endpointPlaceholder(provider) {
  if (provider === "ollama") {
    return "http://192.168.1.10:11434";
  }
  return "https://your-gateway.example";
}

function _endpointHint(provider) {
  if (provider === "ollama") {
    return "Use the host's LAN IP (run `hostname -I` or `ipconfig`). Ollama needs OLLAMA_HOST=0.0.0.0; host.docker.internal is Docker Desktop only. See user guide §3.1.1.";
  }
  return null;
}

function _swapValue(formValue, currentValue) {
  // Returns the next swap field value: null when blank or unchanged
  // (= "keep current"), otherwise the trimmed new value. Prevents the
  // dialog from silently clearing model/provider/endpoint when the
  // operator leaves a field empty (Phase 2 reset-empty-model bug).
  if (!formValue) return null;
  if (formValue === currentValue) return null;
  return formValue;
}

function ResetAICredentialsDialog({ participant, onClose, onSubmit, onFetchModels }) {
  // Smaller cousin of AddParticipantDialog — the AI already exists, the
  // only required field is a fresh API key. Provider/model/endpoint are
  // optional swaps for the "rotated to a different key AND upgraded the
  // model in one go" case.
  const [form, setForm] = useState({
    api_key: "",
    provider: participant.provider,
    model: participant.model,
    api_endpoint: participant.api_endpoint || "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const update = (field) => (ev) => setForm({ ...form, [field]: ev.target.value });

  const submit = async (ev) => {
    ev.preventDefault();
    const needsKey = PROVIDER_DEFAULTS[form.provider]?.needsKey;
    if (needsKey && !form.api_key.trim()) { setError("API key is required"); return; }
    setBusy(true); setError(null);
    try {
      await onSubmit({
        participant_id: participant.id,
        api_key: form.api_key.trim() || null,
        // Send null (= "keep current") when the swap field is blank or
        // unchanged. Sending an empty string would otherwise overwrite
        // the existing model/provider with "" via COALESCE on the server,
        // leaving the AI un-dispatchable until manually re-edited.
        provider: _swapValue(form.provider, participant.provider),
        model: _swapValue(form.model.trim(), participant.model),
        api_endpoint: _swapValue(form.api_endpoint.trim(), participant.api_endpoint || ""),
      });
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(ev) => ev.stopPropagation()}>
        <h2>Reset credentials: {participant.display_name}</h2>
        <p className="dim">
          Rotates the stored API key in place. Message history stays attributed
          to this participant; the next dispatch uses the new key.
        </p>
        <form onSubmit={submit}>
          <label>New API key{!PROVIDER_DEFAULTS[form.provider]?.needsKey && " (optional for ollama)"}
            <input type="password" value={form.api_key}
              onChange={update("api_key")}
              required={PROVIDER_DEFAULTS[form.provider]?.needsKey}
              autoFocus />
            {_keyPrefixWarning(form.provider, form.api_key) && (
              <div className="warn key-warning">
                {_keyPrefixWarning(form.provider, form.api_key)}
              </div>
            )}
          </label>
          <label>Provider (optional swap)
            <select value={form.provider} onChange={update("provider")}>
              <option value="anthropic">anthropic</option>
              <option value="openai">openai</option>
              <option value="gemini">gemini</option>
              <option value="groq">groq</option>
              <option value="ollama">ollama</option>
            </select>
          </label>
          <label>Model (optional swap)
            <input value={form.model} onChange={update("model")} />
          </label>
          <label>API endpoint (optional, for Ollama/custom)
            <input
              value={form.api_endpoint}
              onChange={update("api_endpoint")}
              placeholder={_endpointPlaceholder(form.provider)}
            />
          </label>
          {_endpointHint(form.provider) && (
            <small className="dim">{_endpointHint(form.provider)}</small>
          )}
          {onFetchModels && (
            <ProviderModelPicker
              provider={form.provider}
              apiKey={form.api_key}
              apiEndpoint={form.api_endpoint}
              onFetch={onFetchModels}
              onPick={(picked) => setForm((f) => _applyPickedModel(f, picked))}
            />
          )}
          {error && <div className="error">{error}</div>}
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className={busy ? "busy" : ""} disabled={busy}>
              {busy ? "Resetting…" : "Reset credentials"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SessionView — main authenticated screen
// ---------------------------------------------------------------------------

function PendingSession({ auth, onLogout, onAuthExpired, onApproved }) {
  // Minimal WS-subscribed view for role=pending users. The server
  // filters state_snapshot to session name + humans only; when the
  // facilitator approves, a participant_update arrives with our row
  // flipped to role='participant' and we escalate to SessionView.
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const [denied, setDenied] = useState(false);
  const onEvent = useCallback((event) => {
    dispatch({ type: event.type, event });
    if (event.type === "participant_update"
        && event.participant?.id === auth.participant_id
        && event.participant?.role !== "pending") {
      onApproved({ ...auth, role: event.participant.role });
      return;
    }
    // Facilitator rejected us: the server hard-deletes the row and
    // emits participant_removed. Show the denial notice and redirect
    // to the guest landing instead of sitting in pending limbo.
    if (event.type === "participant_removed"
        && event.participant_id === auth.participant_id) {
      setDenied(true);
    }
  }, [auth, onApproved]);
  useWebSocket(auth.session_id, onEvent, onAuthExpired);
  useEffect(() => {
    if (!denied) return;
    const t = setTimeout(onLogout, 4000);
    return () => clearTimeout(t);
  }, [denied, onLogout]);
  if (denied) {
    return (
      <main className="pending-screen">
        <h1>Request declined</h1>
        <p className="dim">
          The facilitator declined your request to join this session.
          Returning to the sign-in screen…
        </p>
        <button type="button" onClick={onLogout}>Return now</button>
      </main>
    );
  }
  const humans = (state.participants || []).filter((p) => p.provider === "human");
  return <PendingHoldingScreen session={state.session} humans={humans} onLogout={onLogout} />;
}

function SessionView({ auth, onLogout, onAuthExpired }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [editDraft, setEditDraft] = useState(null);
  const [addedToken, setAddedToken] = useState(null);
  const [theme, setTheme] = useState(() => {
    try {
      const stored = localStorage.getItem("sacp-theme");
      if (stored === "dark" || stored === "light") {
        document.documentElement.dataset.theme = stored;
        return stored;
      }
    } catch { /* Safari private mode, etc. — fall back silently */ }
    return document.documentElement.dataset.theme || "dark";
  });

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("sacp-theme", next); } catch { /* persistence best-effort */ }
  };

  const exportTranscript = async (format) => {
    try {
      const path = format === "json" ? "/tools/session/export_json" : "/tools/session/export_markdown";
      const result = await mcpCall(path);
      const blob = new Blob(
        [typeof result.content === "string" ? result.content : JSON.stringify(result, null, 2)],
        { type: format === "json" ? "application/json" : "text/markdown" },
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sacp-${auth.session_id}-${Date.now()}.${format === "json" ? "json" : "md"}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Export failed: ${e.message}`);
    }
  };

  const onEvent = useCallback((event) => {
    if (event?.type) {
      dispatch({ type: event.type, event });
    }
  }, []);

  const onAuthKill = useCallback((code) => {
    dispatch({ type: "ws_state", value: "closed" });
    onAuthExpired?.(code);
  }, [onAuthExpired]);

  const wsState = useWebSocket(auth.session_id, onEvent, onAuthKill);

  useEffect(() => {
    dispatch({ type: "ws_state", value: wsState });
  }, [wsState]);

  // state.me.role is authoritative from the snapshot / participant_update
  // stream. Fall back to auth.role only during the snapshot-arrival window.
  const isFacilitator = (state.me?.role || auth.role) === "facilitator";

  const sendMessage = async (content) => {
    await mcpCall("/tools/participant/inject_message", {
      method: "POST",
      body: { content, priority: 1 },
    });
  };

  const onSessionAction = async (action) => {
    try {
      await mcpCall(`/tools/session/${action}`, { method: "POST" });
    } catch (e) {
      alert(`${action} failed: ${e.message}`);
    }
  };

  const onSummarizeNow = async () => {
    try {
      await mcpCall("/tools/session/summarize_now", { method: "POST" });
    } catch (e) {
      alert(`Summarize failed: ${e.message}`);
    }
  };

  const onLoadSummaryHistory = async () => {
    const result = await mcpCall("/tools/session/list_summaries");
    return result.summaries || [];
  };

  const onLoadReviewGates = async () => {
    const result = await mcpCall("/tools/session/list_review_gates");
    return result.review_gates || [];
  };

  const onExportSummaries = async (fmt) => {
    return await mcpCall(
      `/tools/session/export_summaries?fmt=${encodeURIComponent(fmt)}`,
    );
  };

  const onReviewGateAll = async (preference) => {
    try {
      await mcpCall("/tools/facilitator/set_routing_all_ais", {
        method: "POST",
        body: { preference },
      });
    } catch (e) {
      alert(`Bulk routing change failed: ${e.message}`);
    }
  };

  const addParticipant = async (form) => {
    // Facilitator path supports adding humans + AIs; non-facilitators use
    // the narrower /tools/participant/add_ai endpoint (AI-only, sponsored).
    if (isFacilitator) {
      const result = await mcpCall("/tools/facilitator/add_participant", {
        method: "POST",
        body: form,
      });
      if (form.provider === "human" && result?.auth_token) {
        setAddedToken({ display_name: form.display_name, token: result.auth_token });
      }
      return;
    }
    if (form.provider === "human") {
      throw new Error("Only the facilitator can add human participants");
    }
    await onAddMyAI(form);
  };

  const fetchProviderModels = async ({ provider, api_key, api_endpoint }) => {
    const result = await mcpCall("/tools/provider/list_models", {
      method: "POST",
      body: { provider, api_key, api_endpoint: api_endpoint || null },
    });
    return result.models || [];
  };

  const onRenameSession = async (newName) => {
    try {
      await mcpCall("/tools/session/set_name", {
        method: "POST",
        body: { name: newName },
      });
    } catch (e) {
      alert(`Rename failed: ${e.message}`);
    }
  };

  const onRemoveParticipant = async (p) => {
    const label = p.display_name || p.id;
    if (!confirm(`Remove ${label} from this session?`)) return;
    // Optimistic removal: drop the row from local state so the UI updates
    // immediately; if the server rejects, restore the original snapshot.
    dispatch({ type: "participant_removed", event: { participant_id: p.id } });
    try {
      await mcpCall(
        `/tools/facilitator/remove_participant?participant_id=${encodeURIComponent(p.id)}`,
        { method: "POST" },
      );
    } catch (e) {
      dispatch({ type: "participant_restore", participant: p });
      alert(`Remove failed: ${e.message}`);
    }
  };

  const onResetAI = (p) => setResetTarget(p);

  const onSubmitResetAI = async (body) => {
    await mcpCall("/tools/facilitator/reset_ai_credentials", {
      method: "POST",
      body,
    });
  };

  const onReleaseAI = async (p) => {
    const label = p.display_name || p.id;
    if (!confirm(
      `Release ${label}? Credentials are unbound and the name becomes `
      + `available for re-add. Message history stays linked to this slot.`
    )) return;
    try {
      await mcpCall("/tools/facilitator/release_ai_slot", {
        method: "POST",
        body: { participant_id: p.id },
      });
    } catch (e) {
      alert(`Release failed: ${e.message}`);
    }
  };

  const onAddMyAI = async (form) => {
    await mcpCall("/tools/participant/add_ai", {
      method: "POST",
      body: { ...form, context_window: parseInt(form.context_window, 10) || 0 },
    });
  };

  const onResolveQuestion = (key) => {
    dispatch({ type: "ai_question_dismissed", key });
  };

  const onHonorExit = async (p) => {
    try {
      await mcpCall("/tools/facilitator/set_routing_preference", {
        method: "POST",
        body: { participant_id: p.id, preference: "observer", reason: "honored_exit" },
      });
      dispatch({ type: "ai_exit_dismissed", participant_id: p.id });
    } catch (e) {
      alert(`Honor exit failed: ${e.message}`);
    }
  };

  const onDismissExit = (participantId) => {
    dispatch({ type: "ai_exit_dismissed", participant_id: participantId });
  };

  const onSetBudget = async (participantId, { budget_hourly, budget_daily, max_tokens_per_turn }) => {
    await mcpCall("/tools/facilitator/set_budget", {
      method: "POST",
      body: {
        participant_id: participantId,
        budget_hourly: budget_hourly,
        budget_daily: budget_daily,
        max_tokens_per_turn: max_tokens_per_turn,
      },
    });
  };

  const onRoutingChange = async (participantId, preference) => {
    try {
      // Prefer the self-serve endpoint (T250) when we're editing our own row.
      const isSelf = participantId === auth.participant_id;
      const path = isSelf
        ? "/tools/participant/set_routing_preference"
        : "/tools/facilitator/set_routing_preference";
      const body = isSelf ? { preference } : { participant_id: participantId, preference };
      await mcpCall(path, { method: "POST", body });
    } catch (e) {
      alert(`Routing change failed: ${e.message}`);
    }
  };

  // US5 review-gate actions. overrideReason is provided on re-submission after a
  // 422 (spec 012 FR-006 / Constitution §4.9 approach (b)).
  const approveDraft = async (draftId, overrideReason) => {
    const body = { draft_id: draftId };
    if (overrideReason) body.override_reason = overrideReason;
    await mcpCall("/tools/facilitator/approve_draft", { method: "POST", body });
  };
  const rejectDraft = async (draftId) => {
    await mcpCall("/tools/facilitator/reject_draft", {
      method: "POST", body: { draft_id: draftId, reason: "" },
    });
  };
  const editDraftSave = async (draftId, editedContent, overrideReason) => {
    const body = { draft_id: draftId, edited_content: editedContent };
    if (overrideReason) body.override_reason = overrideReason;
    await mcpCall("/tools/facilitator/edit_draft", { method: "POST", body });
  };
  const togglePauseScope = async (scope) => {
    await mcpCall("/tools/facilitator/set_review_gate_pause_scope", {
      method: "POST", body: { scope },
    });
  };

  // US6 admin actions.
  const approveParticipant = async (pid) => {
    await mcpCall(`/tools/facilitator/approve_participant?participant_id=${encodeURIComponent(pid)}`, { method: "POST" });
  };
  const rejectParticipant = async (pid) => {
    // Optimistic removal: reject hard-deletes the row, so drop it from local
    // state immediately. The server will also broadcast participant_removed,
    // but the optimistic path prevents the 10-click/9x-400 pathology we saw
    // in Test06-Web06 where users kept clicking a stale row.
    const prev = state.participants.find((p) => p.id === pid);
    dispatch({ type: "participant_removed", event: { participant_id: pid } });
    try {
      await mcpCall(
        `/tools/facilitator/reject_participant?participant_id=${encodeURIComponent(pid)}`,
        { method: "POST" },
      );
    } catch (e) {
      if (prev) dispatch({ type: "participant_restore", participant: prev });
      alert(`Reject failed: ${e.message}`);
    }
  };
  const createInvite = async (maxUses) => {
    return await mcpCall(`/tools/facilitator/create_invite?max_uses=${maxUses}`, { method: "POST" });
  };
  const transferFacilitator = async (targetId) => {
    await mcpCall(`/tools/facilitator/transfer_facilitator?target_id=${encodeURIComponent(targetId)}`, { method: "POST" });
  };
  const setSessionConfig = async (action, body) => {
    try {
      await mcpCall(`/tools/facilitator/set_${action}`, { method: "POST", body });
    } catch (e) {
      alert(`Config change failed: ${e.message}`);
    }
  };

  // US7 proposal actions.
  const createProposal = async (topic, position) => {
    await mcpCall("/tools/proposal/create", {
      method: "POST",
      body: { topic, position },
    });
  };
  const voteOnProposal = async (proposalId, vote) => {
    await mcpCall("/tools/proposal/vote", {
      method: "POST",
      body: { proposal_id: proposalId, vote },
    });
  };
  const resolveProposal = async (proposalId, status) => {
    await mcpCall("/tools/proposal/resolve", {
      method: "POST",
      body: { proposal_id: proposalId, status },
    });
  };

  // Seed open + resolved proposals on first WS attach so tallies + history are current.
  useEffect(() => {
    if (!auth.session_id) return;
    mcpCall("/tools/proposal/list?include_resolved=true")
      .then((data) => {
        if (data?.proposals) {
          dispatch({
            type: "seed_proposals",
            proposals: data.proposals,
            resolved: data.resolved || [],
          });
        }
      })
      .catch(() => { /* ignore; snapshot will still deliver open_proposals */ });
  }, [auth.session_id]);

  // Audit log seed — fetched once when the facilitator opens the panel.
  useEffect(() => {
    if (!isFacilitator || state.auditEntries.length > 0) return;
    mcpCall(`/tools/debug/export?session_id=${auth.session_id}`)
      .then((data) => {
        const entries = (data?.logs?.audit || [])
          .map((e) => ({ ...e, timestamp: e.timestamp || null }))
          .reverse();
        if (entries.length > 0) dispatch({ type: "seed_audit_entries", entries });
      })
      .catch(() => { /* non-facilitator will 403; ignore */ });
  }, [isFacilitator, auth.session_id, state.auditEntries.length]);

  return (
    <div className="app-shell">
      <Header
        session={state.session}
        me={auth}
        wsState={wsState}
        onExport={exportTranscript}
        theme={theme}
        onToggleTheme={toggleTheme}
        onRename={onRenameSession}
        isFacilitator={isFacilitator}
      />
      <ErrorToasts
        errors={state.errors}
        onDismiss={(index) => dispatch({ type: "clear_error", index })}
      />
      {wsState === "reconnecting" && (
        <div className="banner banner-warn">
          Reconnecting to the server…
        </div>
      )}
      {state.session?.status === "archived" && (
        <div className="banner banner-warn">
          This session has been archived. The chat is finished and is now read-only.
          {state.latestSummary && " A final summary has been generated below."}
        </div>
      )}
      <div className="app-body">
        <aside className="sidebar-left">
          <SelfControls
            me={auth}
            participants={state.participants}
            isFacilitator={isFacilitator}
            onRoutingChange={onRoutingChange}
          />
          <ParticipantList
            participants={state.participants}
            me={auth}
            skipReasons={state.skipReasons}
            isFacilitator={isFacilitator}
            exitRequests={state.aiExitRequests}
            onRemove={onRemoveParticipant}
            onRoutingChange={onRoutingChange}
            onResetAI={onResetAI}
            onReleaseAI={onReleaseAI}
            onHonorExit={onHonorExit}
            onDismissExit={onDismissExit}
          />
          <SessionControls
            session={state.session}
            isFacilitator={isFacilitator}
            onAction={onSessionAction}
            onSummarize={onSummarizeNow}
            onReviewGateAll={onReviewGateAll}
          />
          {isFacilitator ? (
            <>
              <button className="full-width" onClick={() => setShowAddDialog(true)}>
                + Add participant
              </button>
              <AdminPanel
                participants={state.participants}
                session={state.session}
                auditEntries={state.auditEntries}
                onApprove={approveParticipant}
                onReject={rejectParticipant}
                onInvite={createInvite}
                onTransfer={transferFacilitator}
                onConfig={setSessionConfig}
              />
            </>
          ) : auth && (
            <button className="full-width" onClick={() => setShowAddDialog(true)}>
              + Add my AI
            </button>
          )}
          <button className="full-width logout" onClick={onLogout}>Sign out</button>
        </aside>
        <main className="center-column">
          <Transcript messages={state.messages} participants={state.participants} />
          <MessageInput onSend={sendMessage} disabled={wsState !== "open"} />
        </main>
        <aside className="sidebar-right">
          <ReviewGateQueue
            drafts={state.pendingDrafts}
            participants={state.participants}
            pauseScope={state.session?.review_gate_pause_scope}
            isFacilitator={isFacilitator}
            onApprove={approveDraft}
            onReject={rejectDraft}
            onEdit={(d) => setEditDraft(d)}
            onToggleScope={togglePauseScope}
          />
          <BudgetPanel
            participants={state.participants}
            me={auth}
            isFacilitator={isFacilitator}
            onSetBudget={onSetBudget}
          />
          <ConvergencePanel scores={state.convergenceScores} />
          <SummaryPanel
            summary={state.latestSummary}
            onLoadHistory={onLoadSummaryHistory}
            onLoadReviewGates={onLoadReviewGates}
            onExport={onExportSummaries}
          />
          <ProposalTracker
            proposals={state.openProposals}
            resolved={state.resolvedProposals}
            me={auth}
            isFacilitator={isFacilitator}
            onCreate={createProposal}
            onVote={voteOnProposal}
            onResolve={resolveProposal}
          />
        </aside>
      </div>
      {showAddDialog && (
        <AddParticipantDialog
          onClose={() => setShowAddDialog(false)}
          onAdd={addParticipant}
          onFetchModels={fetchProviderModels}
          aiOnly={!isFacilitator}
        />
      )}
      {editDraft && (
        <ReviewGateEditor
          draft={editDraft}
          onSave={editDraftSave}
          onClose={() => setEditDraft(null)}
        />
      )}
      {addedToken && (
        <AddedParticipantTokenModal entry={addedToken} onClose={() => setAddedToken(null)} />
      )}
      {resetTarget && (
        <ResetAICredentialsDialog
          participant={resetTarget}
          onClose={() => setResetTarget(null)}
          onSubmit={onSubmitResetAI}
          onFetchModels={fetchProviderModels}
        />
      )}
    </div>
  );
}

// Shared "Fetch models" affordance for AddParticipantDialog and
// ResetAICredentialsDialog. Renders a button next to the API key field
// and, after a successful fetch, a quick-pick <select> below it. The
// existing free-text model input stays — picking from the dropdown
// just writes back into it. Operators can still type exotic model names.
function ProviderModelPicker({ provider, apiKey, apiEndpoint, onPick, onFetch }) {
  const [models, setModels] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const needsKey = PROVIDER_DEFAULTS[provider]?.needsKey;
  const needsEndpoint = provider === "ollama";
  const canFetch = (!needsKey || apiKey.trim()) && (!needsEndpoint || apiEndpoint.trim());

  const fetch = async () => {
    setBusy(true); setError(null);
    try {
      const list = await onFetch({ provider, api_key: apiKey, api_endpoint: apiEndpoint });
      setModels(list);
      if (list.length === 0) setError(`No models returned for ${provider}.`);
    } catch (e) {
      setError(e.message || "Fetch failed");
      setModels(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" onClick={fetch} disabled={busy || !canFetch}
        className={"fetch-models-btn" + (busy ? " busy" : "")}>
        {busy ? "Fetching…" : "Fetch models"}
      </button>
      {error && <div className="warn key-warning">{error}</div>}
      {models && models.length > 0 && (
        <label>Pick a model
          <select value="" onChange={(ev) => ev.target.value && onPick(ev.target.value)}>
            <option value="">— pick from {models.length} fetched —</option>
            {models.map((m) => (
              <option key={m.model} value={m.model}>{m.display}</option>
            ))}
          </select>
        </label>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

function App() {
  const [auth, setAuth] = useState(null);
  const [banner, setBanner] = useState(null);
  // `restoring` gates the first render: while the cookie-restore call
  // is in flight we must not render AuthGate or we'd briefly show the
  // landing page on every refresh. Null = unknown / in-flight;
  // 'done' = resolved (either auth set or confirmed no session).
  const [restoring, setRestoring] = useState("pending");

  useEffect(() => {
    // Attempt cookie-based session restore on first mount so F5 doesn't
    // kick the user back to landing. /me succeeds only when a valid
    // HttpOnly cookie is already in place; 401 is the normal "no
    // session yet" case and we silently fall through.
    let cancelled = false;
    uiCall("/me", { method: "GET" })
      .then((result) => { if (!cancelled) setAuth(result); })
      .catch(() => { /* no cookie — show landing */ })
      .finally(() => { if (!cancelled) setRestoring("done"); });
    return () => { cancelled = true; };
  }, []);

  const logout = async () => {
    try {
      await uiCall("/logout", { method: "POST" });
    } catch (e) {
      console.warn("logout failed:", e);
    }
    setAuth(null);
  };

  const onAuthExpired = useCallback((code) => {
    const msg = code === WS_CLOSE_FORBIDDEN
      ? "You were removed from this session."
      : "Your session expired — please sign in again.";
    setBanner(msg);
    setAuth(null);
  }, []);

  const onLogin = useCallback((result) => {
    setBanner(null);
    setAuth(result);
  }, []);

  if (restoring === "pending") {
    return <main className="auth-gate"><p className="dim">Restoring session…</p></main>;
  }
  if (!auth) return <AuthGate banner={banner} onLogin={onLogin} />;
  if (auth.role === "pending") {
    return <PendingSession auth={auth} onLogout={logout} onAuthExpired={onAuthExpired} onApproved={setAuth} />;
  }
  return <SessionView auth={auth} onLogout={logout} onAuthExpired={onAuthExpired} />;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
