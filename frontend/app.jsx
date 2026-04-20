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
      const others = state.messages.filter((m) => m.turn_number !== incoming.turn_number);
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
    case "error":
      return {
        ...state,
        errors: [...state.errors, { code: action.event.code, message: action.event.message }],
      };
    case "clear_error":
      return { ...state, errors: state.errors.filter((_, i) => i !== action.index) };
    default:
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

function Header({ session, me, wsState }) {
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
        <span className="ws-indicator" style={{ backgroundColor: dotColor }} title={dotTitle} />
        <span className="me">{me?.participant_id}</span>
      </div>
    </header>
  );
}

function ParticipantList({ participants, me }) {
  // US2 T073: pending participants render with a badge but no action surfaces.
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
            <span>{p.status}</span>
            {p.consecutive_timeouts > 0 && <span className="warn">⚠ {p.consecutive_timeouts}</span>}
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

  const isFacilitator =
    state.me?.role === "facilitator" || auth.role === "facilitator";

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
      await mcpCall("/tools/facilitator/set_routing_preference", auth.token, {
        method: "POST",
        body: { participant_id: participantId, preference },
      });
    } catch (e) {
      alert(`Routing change failed: ${e.message}`);
    }
  };

  return (
    <div className="app-shell">
      <Header session={state.session} me={auth} wsState={wsState} />
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
          <ParticipantList participants={state.participants} me={auth} />
          <SessionControls
            session={state.session}
            isFacilitator={isFacilitator}
            onAction={onSessionAction}
          />
          {isFacilitator && (
            <button className="full-width" onClick={() => setShowAddDialog(true)}>
              + Add participant
            </button>
          )}
          <button className="full-width logout" onClick={onLogout}>Sign out</button>
        </aside>
        <main className="center-column">
          <Transcript messages={state.messages} participants={state.participants} />
          <MessageInput onSend={sendMessage} disabled={wsState !== "open"} />
        </main>
        <aside className="sidebar-right">
          <div className="panel">
            <h2>Review gate</h2>
            {state.pendingDrafts.length === 0 ? (
              <p className="dim">No pending drafts.</p>
            ) : (
              state.pendingDrafts.map((d) => (
                <div key={d.id} className="draft-stub">
                  <strong>{d.participant_id}</strong>
                  <p className="dim">Approval UI ships in Phase 2c.</p>
                </div>
              ))
            )}
          </div>
          <div className="panel">
            <h2>Convergence</h2>
            <p className="dim">
              last score: {state.convergenceScores.at(-1)?.similarity_score?.toFixed(3) ?? "—"}
            </p>
          </div>
        </aside>
      </div>
      {showAddDialog && (
        <AddParticipantDialog
          onClose={() => setShowAddDialog(false)}
          onAdd={addParticipant}
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
