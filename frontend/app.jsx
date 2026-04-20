/* SACP Web UI — Phase 2a / Phase 3 US1 MVP facilitator flow.
 *
 * Single-file React SPA. All components live here; split into
 * frontend/components/*.jsx when this file crosses ~2000 lines
 * (FR-002). Loaded via Babel Standalone at the bottom of index.html.
 *
 * What's here (T050–T057):
 *   - AuthGate: bearer-token login → POST /login → cookie + React-ref token
 *   - SessionView: three-column shell, WebSocket wiring, state reducer
 *   - Header: session name, status, turn counter, connection indicator
 *   - ParticipantList: cards with role badge + provider + routing mode
 *   - Transcript: marked + DOMPurify hardened markdown render
 *   - MessageInput: textarea with Ctrl+Enter → inject_message
 *   - SessionControls: facilitator-only pause/resume/start/stop/archive
 *   - AddParticipantDialog: facilitator-only modal for new participants
 *
 * What's not here yet:
 *   - Review gate queue (T110 / Phase 8)
 *   - Budget / convergence / summary panels (Phase 2b)
 *   - Proposals (Phase 2c)
 *   - Robust reconnect loop + client-side state reducer module split (T080–T085)
 *     — basic reconnect-on-close is in useWebSocket; full resilience in US3.
 */

const { useState, useEffect, useReducer, useCallback, useRef, useMemo } = React;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const MCP_BASE = (() => {
  // The MCP API lives on port 8750 of the same host as the Web UI (8751).
  // Operators can override via window.__SACP_MCP_BASE__ before app.jsx loads.
  if (window.__SACP_MCP_BASE__) return window.__SACP_MCP_BASE__;
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8750`;
})();

const WS_BASE = (() => {
  const { protocol, host } = window.location;
  const wsProto = protocol === "https:" ? "wss:" : "ws:";
  return `${wsProto}//${host}`;
})();

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
// Markdown rendering (security overrides are deepened in Phase 6 / US8)
// ---------------------------------------------------------------------------

function renderMarkdown(content) {
  if (!content) return "";
  const raw = marked.parse(content, { breaks: true });
  return DOMPurify.sanitize(raw, {
    FORBID_TAGS: ["script", "iframe", "object", "embed", "style", "form"],
    FORBID_ATTR: ["onerror", "onload", "onclick"],
  });
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
    errors: [],
  };
}

function reducer(state, action) {
  switch (action.type) {
    case "ws_state":
      return { ...state, wsState: action.value };
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
      // message events currently carry a minimal shape from _broadcast_turn_to_web_ui;
      // the Transcript also receives full records via the state_snapshot. Merge by turn.
      const existing = state.messages.filter((m) => m.turn_number !== incoming.turn_number);
      return { ...state, messages: [...existing, incoming].sort((a, b) => a.turn_number - b.turn_number) };
    }
    case "participant_update": {
      const updated = action.event.participant;
      const others = state.participants.filter((p) => p.id !== updated.id);
      return { ...state, participants: [...others, updated] };
    }
    case "session_status_changed":
      return { ...state, session: { ...(state.session || {}), status: action.event.status } };
    case "convergence_update":
      return { ...state, convergenceScores: [...state.convergenceScores, action.event.point].slice(-50) };
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
      return { ...state, errors: [...state.errors, { code: action.event.code, message: action.event.message }] };
    case "clear_error":
      return { ...state, errors: state.errors.filter((_, i) => i !== action.index) };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// WebSocket client (lightweight; Phase 5 adds exponential backoff + full resilience)
// ---------------------------------------------------------------------------

function useWebSocket(sessionId, onEvent) {
  const [state, setState] = useState("connecting");
  const wsRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return;
    let closed = false;

    const connect = () => {
      const ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);
      wsRef.current = ws;
      ws.onopen = () => setState("open");
      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data);
          onEvent(event);
        } catch (e) {
          console.warn("failed to parse WS event", e);
        }
      };
      ws.onclose = (ev) => {
        if (closed) return;
        if (ev.code === 4401 || ev.code === 4403) {
          setState("closed");
          return;
        }
        setState("reconnecting");
        setTimeout(connect, 2000);
      };
      ws.onerror = () => setState("reconnecting");
    };

    connect();
    return () => {
      closed = true;
      if (wsRef.current) wsRef.current.close();
    };
  }, [sessionId, onEvent]);

  return state;
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function AuthGate({ onLogin }) {
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
  return (
    <header className="app-header">
      <div className="header-left">
        <strong>{session?.name || "…"}</strong>
        <span className={`status-badge status-${session?.status || "unknown"}`}>{session?.status || "?"}</span>
      </div>
      <div className="header-center">
        <span>Turn {session?.current_turn ?? 0}</span>
      </div>
      <div className="header-right">
        <span className="ws-indicator" style={{ backgroundColor: dotColor }} title={wsState} />
        <span className="me">{me?.participant_id}</span>
      </div>
    </header>
  );
}

function ParticipantList({ participants, me }) {
  const ordered = useMemo(
    () => [...participants].sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [participants],
  );
  return (
    <section className="panel participant-list">
      <h2>Participants</h2>
      {ordered.length === 0 && <p className="dim">none</p>}
      {ordered.map((p) => (
        <div key={p.id} className={`participant-card role-${p.role} status-${p.status}`}>
          <div className="p-row">
            <strong>{p.display_name}</strong>
            {p.id === me?.participant_id && <span className="badge badge-you">you</span>}
          </div>
          <div className="p-meta">
            <span>{p.role}</span>
            <span>·</span>
            <span>{p.provider}</span>
            {p.model_family && <>
              <span>·</span>
              <span>{p.model_family}</span>
            </>}
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

function Transcript({ messages, participants }) {
  const byId = useMemo(() => Object.fromEntries(participants.map((p) => [p.id, p])), [participants]);
  return (
    <section className="transcript">
      {messages.length === 0 && <p className="dim">No messages yet.</p>}
      {messages.map((m) => {
        const speaker = byId[m.speaker_id];
        const html = renderMarkdown(m.content || "");
        return (
          <article key={`${m.turn_number}-${m.speaker_id}`} className={`msg msg-${m.speaker_type}`}>
            <header>
              <strong>{speaker?.display_name || m.speaker_id}</strong>
              <span className="msg-type">{m.speaker_type}</span>
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
// SessionView (main authenticated screen)
// ---------------------------------------------------------------------------

function SessionView({ auth, onLogout }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const [showAddDialog, setShowAddDialog] = useState(false);

  const onEvent = useCallback((event) => {
    if (event?.type) {
      dispatch({ type: event.type, event });
    }
  }, []);

  const wsState = useWebSocket(auth.session_id, onEvent);

  useEffect(() => {
    dispatch({ type: "ws_state", value: wsState });
  }, [wsState]);

  const isFacilitator = state.me?.role === "facilitator" || auth.role === "facilitator";

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

  return (
    <div className="app-shell">
      <Header session={state.session} me={auth} wsState={wsState} />
      <div className="app-body">
        <aside className="sidebar-left">
          <ParticipantList participants={state.participants} me={auth} />
          <SessionControls session={state.session} isFacilitator={isFacilitator} onAction={onSessionAction} />
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
        <AddParticipantDialog onClose={() => setShowAddDialog(false)} onAdd={addParticipant} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

function App() {
  const [auth, setAuth] = useState(null);

  const logout = async () => {
    try {
      await uiCall("/logout", { method: "POST" });
    } catch (e) {
      console.warn("logout failed:", e);
    }
    setAuth(null);
  };

  if (!auth) return <AuthGate onLogin={setAuth} />;
  return <SessionView auth={auth} onLogout={logout} />;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
