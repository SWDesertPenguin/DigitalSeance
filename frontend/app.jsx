/* SACP Web UI root — Phase 2a scaffold.
 *
 * Current responsibility: prove the CDN + Babel Standalone + CSP chain
 * all light up end-to-end. Real components (AuthGate, SessionView, etc.)
 * land in subsequent tasks.
 */

const { useState, useEffect } = React;

function App() {
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    fetch("/healthz")
      .then((r) => r.json())
      .then((j) => setStatus(j.status || "unknown"))
      .catch(() => setStatus("error"));
  }, []);

  return (
    <main className="scaffold">
      <h1>SACP Web UI</h1>
      <p>Scaffold online. Health: <code>{status}</code></p>
      <p className="dim">Phase 2a implementation in progress.</p>
    </main>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
