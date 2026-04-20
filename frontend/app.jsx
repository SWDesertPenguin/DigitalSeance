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

const MCP_BASE = (() => {
  if (window.__SACP_MCP_BASE__) return window.__SACP_MCP_BASE__;
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8750`;
})();

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

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function _fetchJson(url, opts = {}) {
  const res = await fetch(url, opts);
  const contentType = res.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = typeof body === "object" && body?.detail ? body.detail : body;
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return body;
}

function mcpCall(path, token, { method = "GET", body = null } = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-SACP-Request": "1",
    Authorization: `Bearer ${token}`,
  };
  const opts = { method, headers };
  if (body !== null) opts.body = JSON.stringify(body);
  return _fetchJson(`${MCP_BASE}${path}`, opts);
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

function initialState() {
  return {
    session: null,
    me: null,
    participants: [],
    messages: [],
    pendingDrafts: [],
    openProposals: [],
    latestSummary: null,
    convergenceScores: [],
    auditEntries: [],      // Phase 2b: fed by T252 audit_entry WS events
    skipReasons: {},       // { participant_id: [{reason, timestamp}, ...] } (last 3 per pid)
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
      return {
        ...state,
        messages: [...others, incoming].sort((a, b) => a.turn_number - b.turn_number),
      };
    }
    case "participant_update": {
      const updated = action.event.participant;
      const others = state.participants.filter((p) => p.id !== updated.id);
      return { ...state, participants: [...others, updated] };
    }
    case "session_status_changed":
      return { ...state, session: { ...(state.session || {}), status: action.event.status } };
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
      return { ...state, openProposals: action.proposals };
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
      };
    case "error":
      return {
        ...state,
        errors: [...state.errors, { code: action.event.code, message: action.event.message }],
      };
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
  const [token, setToken] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (ev) => {
    ev.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uiCall("/login", { method: "POST", body: { token: token.trim() } });
      onLogin(result);
    } catch (e) {
      setError(e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-gate">
      <h1>SACP Web UI</h1>
      {banner && <div className="banner banner-warn">{banner}</div>}
      <p className="dim">Paste your participant bearer token to continue.</p>
      <form onSubmit={submit}>
        <input
          type="password"
          placeholder="bearer token"
          value={token}
          onChange={(ev) => setToken(ev.target.value)}
          autoFocus
        />
        <button type="submit" disabled={busy || !token.trim()}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <div className="error">{error}</div>}
      </form>
    </main>
  );
}

function Header({ session, me, wsState, onExport, theme, onToggleTheme }) {
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
        <strong>{session?.name || "…"}</strong>
        <span className={`status-badge status-${session?.status || "unknown"}`}>
          {session?.status || "?"}
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

function ParticipantList({ participants, me, skipReasons }) {
  // US2 T073 + US10 T140–T142.
  const visible = useMemo(
    () => [...participants].sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [participants],
  );
  return (
    <section className="panel participant-list">
      <h2>Participants</h2>
      {visible.length === 0 && <p className="dim">none</p>}
      {visible.map((p) => (
        <div key={p.id} className={`participant-card role-${p.role} status-${p.status}`}>
          <div className="p-row">
            <strong>{p.display_name}</strong>
            {p.id === me?.participant_id && <span className="badge badge-you">you</span>}
            {p.status === "pending" && <span className="badge badge-pending">pending</span>}
          </div>
          <div className="p-meta">
            <span>{p.role}</span>
            <span>·</span>
            <span>{p.provider}</span>
            {p.model_family && <><span>·</span><span>{p.model_family}</span></>}
          </div>
          <div className="p-meta">
            <HealthBadge participant={p} skipReasons={skipReasons?.[p.id]} />
            <span className="routing">{p.routing_preference}</span>
          </div>
        </div>
      ))}
    </section>
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
    ? `$${(spend || 0).toFixed(2)} / $${self.budget_daily}`
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
      <div className="kv">
        <span className="dim">routing</span>
        {isFacilitator ? (
          <select
            value={self.routing_preference}
            onChange={(ev) => onRoutingChange(self.id, ev.target.value)}
          >
            {ROUTING_PREFERENCES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        ) : (
          <span title="facilitator-only until T250 lands">{self.routing_preference} 🔒</span>
        )}
      </div>
    </section>
  );
}

function Transcript({ messages, participants }) {
  const byId = useMemo(
    () => Object.fromEntries(participants.map((p) => [p.id, p])),
    [participants],
  );
  return (
    <section className="transcript">
      {messages.length === 0 && <p className="dim">No messages yet.</p>}
      {messages.map((m) => {
        const speaker = byId[m.speaker_id];
        const html = renderMarkdown(m.content || "");
        const hiddenCount = countInvisibles(m.content || "");
        return (
          <article
            key={`${m.turn_number}-${m.speaker_id}`}
            className={`msg msg-${m.speaker_type}`}
          >
            <header>
              <strong>{speaker?.display_name || m.speaker_id}</strong>
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
  const title = skipReasons && skipReasons.length > 0
    ? skipReasons.map((s) => `#${s.turn_number}: ${s.reason}`).join("\n")
    : health.label;
  return (
    <span className={`health-badge health-${health.tone}`} title={title}>
      {health.label}
    </span>
  );
}

function pctColor(pct) {
  if (pct >= 0.95) return "var(--danger)";
  if (pct >= 0.50) return "var(--warning)";
  return "var(--ok)";
}

function BudgetPanel({ participants, me, isFacilitator }) {
  // US4 T100–T102. Renders one card per participant. Self + facilitator see
  // dollar amounts; others only see utilization %.
  const list = useMemo(
    () => participants
      .filter((p) => p.provider !== "human")
      .sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [participants],
  );
  if (list.length === 0) {
    return (
      <section className="panel budget-panel">
        <h2>Budget</h2>
        <p className="dim">No AI participants yet.</p>
      </section>
    );
  }
  return (
    <section className="panel budget-panel">
      <h2>Budget</h2>
      {list.map((p) => {
        const isSelf = p.id === me?.participant_id;
        const showDollars = isFacilitator || isSelf;
        const daily = p.budget_daily;
        const utilization = daily && p.spend_daily ? Math.min(1, p.spend_daily / daily) : null;
        return (
          <div key={p.id} className="budget-card">
            <div className="p-row">
              <strong>{p.display_name}</strong>
              {showDollars && daily && (
                <span className="dim">${(p.spend_daily ?? 0).toFixed(3)} / ${daily}</span>
              )}
            </div>
            {utilization !== null ? (
              <div className="util-bar">
                <div
                  className="util-fill"
                  style={{ width: `${Math.round(utilization * 100)}%`, background: pctColor(utilization) }}
                />
                {!showDollars && <span className="util-pct">{Math.round(utilization * 100)}%</span>}
              </div>
            ) : (
              <p className="dim">no daily cap</p>
            )}
          </div>
        );
      })}
    </section>
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

function SummaryPanel({ summary }) {
  // US9 T130–T133.
  const [open, setOpen] = useState(true);
  if (!summary) {
    return (
      <section className="panel">
        <h2>Summary</h2>
        <p className="dim">No checkpoint yet — summaries run every 10 turns.</p>
      </section>
    );
  }
  const { decisions = [], open_questions = [], key_positions = [], narrative } = summary;
  return (
    <section className="panel summary-panel">
      <div className="panel-header" onClick={() => setOpen(!open)}>
        <h2>Summary (turn {summary.turn_number})</h2>
        <span className="toggle">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
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
      )}
    </section>
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
      {drafts.map((d) => {
        const speaker = byId[d.participant_id];
        const preview = (d.draft_content || "").slice(0, 240);
        return (
          <div key={d.id} className="draft-card">
            <header>
              <strong>{speaker?.display_name || d.participant_id}</strong>
              <span className="dim">{d.created_at ? new Date(d.created_at).toLocaleTimeString() : ""}</span>
            </header>
            <div className="draft-body">
              <pre>{preview}{d.draft_content.length > 240 ? "…" : ""}</pre>
            </div>
            {isFacilitator && (
              <div className="draft-actions">
                <button onClick={() => onApprove(d.id)}>Approve</button>
                <button onClick={() => onEdit(d)}>Edit</button>
                <button onClick={() => onReject(d.id)} className="danger">Reject</button>
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}

function ReviewGateEditor({ draft, onSave, onClose }) {
  const [text, setText] = useState(draft.draft_content);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onSave(draft.id, text);
      onClose();
    } catch (e) {
      setError(e.message);
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
          onChange={(ev) => setText(ev.target.value)}
          disabled={busy}
        />
        {error && <div className="error">{error}</div>}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button onClick={submit} disabled={busy || !text.trim()}>
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
    () => participants.filter((p) => p.status === "pending"),
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
                <code>{invite.invite_token}</code>
                <button onClick={() => copy(invite.invite_token)}>Copy</button>
                <p className="dim">Paste this token into another participant's sign-in. Accept flow is Phase 2c.</p>
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

function ProposalTracker({ proposals, me, isFacilitator, onCreate, onVote, onResolve }) {
  // US7 T151–T153.
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

function MessageInput({ onSend, disabled }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const send = async () => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
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
        rows={3}
      />
      <div className="input-actions">
        <span className="dim">Ctrl+Enter to send</span>
        <button onClick={send} disabled={disabled || busy || !text.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}

function SessionControls({ session, isFacilitator, onAction }) {
  if (!isFacilitator) return null;
  const canStart = session?.status === "active";
  return (
    <section className="panel session-controls">
      <h2>Session</h2>
      <div className="button-row">
        <button onClick={() => onAction("start_loop")} disabled={!canStart}>Start loop</button>
        <button onClick={() => onAction("stop_loop")}>Stop loop</button>
      </div>
      <div className="button-row">
        <button onClick={() => onAction("pause")}>Pause</button>
        <button onClick={() => onAction("resume")}>Resume</button>
      </div>
      <div className="button-row">
        <button onClick={() => onAction("archive")} className="danger">Archive</button>
      </div>
    </section>
  );
}

function AddParticipantDialog({ onClose, onAdd }) {
  const [form, setForm] = useState({
    display_name: "",
    provider: "human",
    model: "human",
    model_tier: "n/a",
    model_family: "human",
    context_window: 0,
    api_key: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const update = (field) => (ev) => setForm({ ...form, [field]: ev.target.value });

  const submit = async (ev) => {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onAdd({ ...form, context_window: parseInt(form.context_window, 10) || 0 });
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
        <h2>Add participant</h2>
        <form onSubmit={submit}>
          <label>Display name
            <input value={form.display_name} onChange={update("display_name")} required />
          </label>
          <label>Provider
            <select value={form.provider} onChange={update("provider")}>
              <option value="human">human</option>
              <option value="anthropic">anthropic</option>
              <option value="openai">openai</option>
              <option value="ollama">ollama</option>
            </select>
          </label>
          {isAI && (
            <>
              <label>Model
                <input value={form.model} onChange={update("model")} placeholder="e.g. gpt-4o-mini" required />
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
              <label>API key
                <input type="password" value={form.api_key} onChange={update("api_key")} required />
              </label>
            </>
          )}
          {error && <div className="error">{error}</div>}
          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" disabled={busy || !form.display_name}>
              {busy ? "Adding…" : "Add"}
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

function SessionView({ auth, onLogout, onAuthExpired }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [editDraft, setEditDraft] = useState(null);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "dark");

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
  };

  const exportTranscript = async (format) => {
    try {
      const path = format === "json" ? "/tools/session/export_json" : "/tools/session/export_markdown";
      const result = await mcpCall(path, auth.token);
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
    await mcpCall("/tools/participant/inject_message", auth.token, {
      method: "POST",
      body: { content, priority: 1 },
    });
  };

  const onSessionAction = async (action) => {
    try {
      await mcpCall(`/tools/session/${action}`, auth.token, { method: "POST" });
    } catch (e) {
      alert(`${action} failed: ${e.message}`);
    }
  };

  const addParticipant = async (form) => {
    await mcpCall("/tools/facilitator/add_participant", auth.token, {
      method: "POST",
      body: form,
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
      await mcpCall(path, auth.token, { method: "POST", body });
    } catch (e) {
      alert(`Routing change failed: ${e.message}`);
    }
  };

  // US5 review-gate actions.
  const approveDraft = async (draftId) => {
    await mcpCall("/tools/facilitator/approve_draft", auth.token, {
      method: "POST", body: { draft_id: draftId },
    });
  };
  const rejectDraft = async (draftId) => {
    await mcpCall("/tools/facilitator/reject_draft", auth.token, {
      method: "POST", body: { draft_id: draftId, reason: "" },
    });
  };
  const editDraftSave = async (draftId, editedContent) => {
    await mcpCall("/tools/facilitator/edit_draft", auth.token, {
      method: "POST", body: { draft_id: draftId, edited_content: editedContent },
    });
  };
  const togglePauseScope = async (scope) => {
    await mcpCall("/tools/facilitator/set_review_gate_pause_scope", auth.token, {
      method: "POST", body: { scope },
    });
  };

  // US6 admin actions.
  const approveParticipant = async (pid) => {
    await mcpCall(`/tools/facilitator/approve_participant?participant_id=${encodeURIComponent(pid)}`, auth.token, { method: "POST" });
  };
  const rejectParticipant = async (pid) => {
    await mcpCall(`/tools/facilitator/reject_participant?participant_id=${encodeURIComponent(pid)}`, auth.token, { method: "POST" });
  };
  const createInvite = async (maxUses) => {
    return await mcpCall(`/tools/facilitator/create_invite?max_uses=${maxUses}`, auth.token, { method: "POST" });
  };
  const transferFacilitator = async (targetId) => {
    await mcpCall(`/tools/facilitator/transfer_facilitator?target_id=${encodeURIComponent(targetId)}`, auth.token, { method: "POST" });
  };
  const setSessionConfig = async (action, body) => {
    try {
      await mcpCall(`/tools/facilitator/set_${action}`, auth.token, { method: "POST", body });
    } catch (e) {
      alert(`Config change failed: ${e.message}`);
    }
  };

  // US7 proposal actions.
  const createProposal = async (topic, position) => {
    await mcpCall("/tools/proposal/create", auth.token, {
      method: "POST",
      body: { topic, position },
    });
  };
  const voteOnProposal = async (proposalId, vote) => {
    await mcpCall("/tools/proposal/vote", auth.token, {
      method: "POST",
      body: { proposal_id: proposalId, vote },
    });
  };
  const resolveProposal = async (proposalId, status) => {
    await mcpCall("/tools/proposal/resolve", auth.token, {
      method: "POST",
      body: { proposal_id: proposalId, status },
    });
  };

  // Seed open proposals on first WS attach so tallies are current.
  useEffect(() => {
    if (!auth.session_id) return;
    mcpCall("/tools/proposal/list", auth.token)
      .then((data) => {
        if (data?.proposals) dispatch({ type: "seed_proposals", proposals: data.proposals });
      })
      .catch(() => { /* ignore; snapshot will still deliver open_proposals */ });
  }, [auth.session_id, auth.token]);

  // Audit log seed — fetched once when the facilitator opens the panel.
  useEffect(() => {
    if (!isFacilitator || state.auditEntries.length > 0) return;
    mcpCall(`/tools/debug/export?session_id=${auth.session_id}`, auth.token)
      .then((data) => {
        const entries = (data?.logs?.audit || [])
          .map((e) => ({ ...e, timestamp: e.timestamp || null }))
          .reverse();
        if (entries.length > 0) dispatch({ type: "seed_audit_entries", entries });
      })
      .catch(() => { /* non-facilitator will 403; ignore */ });
  }, [isFacilitator, auth.session_id, auth.token, state.auditEntries.length]);

  return (
    <div className="app-shell">
      <Header
        session={state.session}
        me={auth}
        wsState={wsState}
        onExport={exportTranscript}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      {wsState === "reconnecting" && (
        <div className="banner banner-warn">
          Reconnecting to the server…
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
          />
          <SessionControls
            session={state.session}
            isFacilitator={isFacilitator}
            onAction={onSessionAction}
          />
          {isFacilitator && (
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
          />
          <ConvergencePanel scores={state.convergenceScores} />
          <SummaryPanel summary={state.latestSummary} />
          <ProposalTracker
            proposals={state.openProposals}
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
        />
      )}
      {editDraft && (
        <ReviewGateEditor
          draft={editDraft}
          onSave={editDraftSave}
          onClose={() => setEditDraft(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

function App() {
  const [auth, setAuth] = useState(null);
  const [banner, setBanner] = useState(null);

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

  if (!auth) return <AuthGate banner={banner} onLogin={onLogin} />;
  return <SessionView auth={auth} onLogout={logout} onAuthExpired={onAuthExpired} />;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
