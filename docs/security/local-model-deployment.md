# Local-model deployment security guidance

> Audience: SACP operators and participants planning to run a local model server — Ollama or vLLM — as the backing inference for one or more SACP AI participants. Phase 4 of the SACP roadmap (federation, multi-orchestrator, OAuth 2.1, local-model support, step-up auth) is planned, not yet shipped; this document captures the deployment-side controls that the orchestrator does not enforce on the operator's behalf.

## 1. The default-bind problem

Local inference servers ship with thin or no built-in authentication. The two paths SACP plans to support in Phase 4 both have the same shape: a single HTTP listener that, on a non-loopback bind, will accept any request that reaches it.

**Ollama.** Binds `127.0.0.1:11434` by default. Setting `OLLAMA_HOST` to a non-loopback value (for example `0.0.0.0:11434` or a LAN address) moves the listener onto that interface with no added authentication. The server has no native bearer-token, mTLS, or OAuth surface. The project has shipped multiple RCE-class CVEs in this class — CVE-2024-37032 (path traversal → RCE via the chat endpoint, fixed in 0.1.34) being the most prominent — so an exposed `:11434` is not just an unauthenticated inference endpoint, it is an unauthenticated endpoint with a non-trivial RCE history.

**vLLM.** The `vllm serve` (OpenAI-compatible) server takes `--host` and `--port` arguments. `--api-key TOKEN` enables a single shared bearer that all clients present in the `Authorization: Bearer` header. The token is a single value, not rotatable without a server restart, and is shipped in cleartext unless the listener is fronted by TLS. Without `--api-key`, the listener is unauthenticated.

The orchestrator treats both of these as untrusted upstreams (the seven-layer pipeline still validates responses) but the listener itself is the operator's responsibility.

## 2. SACP's responsibility boundary

SACP does NOT:

- probe the configured `api_endpoint` for unauthenticated access before dispatch,
- enforce TLS on the endpoint scheme (`http://` and `https://` URLs are both accepted),
- require a Bearer token on outbound calls to the participant's endpoint (the orchestrator sends whatever the participant config specifies, including no auth),
- scan the upstream's version banner against a known-vulnerable list,
- distinguish a local-loopback endpoint from a public LAN/WAN endpoint at validation time.

The orchestrator's complementary SSRF defenses (DNS pinning, Host-header preservation, SNI extension on the validated address, allowlist of resolvable target shapes) live at [`docs/red-team-runbook.md`](../red-team-runbook.md) §P.1. Those defenses prevent the orchestrator from being weaponized against an operator's internal network. They do not protect the local-model server itself — that is what this document is about.

If you bind Ollama or vLLM to a network you do not fully control, you accept the consequences of that bind. The orchestrator will route to it because you told it to.

## 3. Single-host pattern

The orchestrator and the local-model server run on the same Docker host or VM, and the model server stays on loopback.

**Ollama.** Default behavior is correct — do nothing. Verify the bind:

```
ss -tlnp | grep 11434
```

Expected output binds only `127.0.0.1:11434` (or `[::1]:11434`). If you see `0.0.0.0:11434` or a LAN address, something — a systemd override, a wrapper script, an `OLLAMA_HOST` in the environment — has moved the listener. Find and revert it before continuing.

**vLLM.** Pass `--host 127.0.0.1` explicitly. The default has historically varied across releases; do not rely on it. Verify with the same `ss -tlnp` check against the chosen port.

If the orchestrator runs in Docker and the model server runs on the host, use the Docker-bridge variant in [`docs/user-guide.md`](../user-guide.md) §3.1.1 (Option B) — that is still a "loopback-equivalent" pattern because the bridge address is not externally routable.

## 4. Multi-host reverse-proxy pattern

The orchestrator and the model server run on different hosts. The model server stays on loopback; a reverse proxy on the model host terminates TLS and enforces a Bearer token. The model server itself is never exposed.

The example below is illustrative — adapt the cert paths, token name, and listener address to your environment.

```caddy
# /etc/caddy/Caddyfile on the model host
models.example.internal {
    tls /etc/caddy/certs/models.crt /etc/caddy/certs/models.key

    @authorized header Authorization "Bearer {env.OLLAMA_PROXY_TOKEN}"

    handle @authorized {
        reverse_proxy 127.0.0.1:11434
    }

    handle {
        respond "Unauthorized" 401
    }
}
```

Keep the upstream bind on loopback:

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
```

SACP participant config: `api_endpoint = https://models.example.internal`, and the participant's `api_key` is the value the proxy expects in `Authorization: Bearer`.

**nginx variant.** Same shape using either `auth_request` to a small auth helper, or an `if ($http_authorization != "Bearer ...")` guard plus `proxy_pass http://127.0.0.1:11434/`. The `auth_request` form is cleaner; the `if` form is shorter. Either works.

**vLLM variant.** Bind `--host 127.0.0.1`, set `--api-key` on the vLLM listener as defense-in-depth, terminate TLS and authenticate at the same reverse-proxy layer. The proxy's Bearer is the value SACP uses; the vLLM `--api-key` is a separate value the proxy injects on the upstream call.

## 5. Hostile-network warnings

Do not run a local model server with a non-loopback bind on:

- coffee-shop, hotel, conference, or airport Wi-Fi,
- a shared university or co-working LAN,
- a residential network with untrusted IoT devices on the same VLAN,
- a cloud VPC subnet that other tenants or services can reach.

If the orchestrator and the model server have to communicate across a hostile or semi-hostile network, tunnel the connection — WireGuard, Tailscale, Headscale, or an SSH `LocalForward`. The tunnel becomes the trust boundary; the model server stays on loopback at both ends.

The reverse-proxy pattern in §4 is appropriate for a trusted server-to-server LAN with TLS. It is not appropriate as the only control on an open network.

## 6. Verification checklist before turning on a local-model participant

- `ss -tlnp | grep <port>` shows the model-server listener bound only to loopback, the Docker bridge gateway, or an explicitly trusted interface. Never `0.0.0.0` on a non-trusted network.
- If the endpoint is reachable off-host, a reverse proxy terminates TLS and requires a Bearer token. The cert is valid for the hostname the orchestrator dials.
- The model host's outbound firewall is restricted to what the model server actually needs (model pulls, dependency updates). The model server has no business making arbitrary outbound calls.
- The model server binary is on a recent release — at minimum, past the CVE-2024-37032 fix for Ollama, and within the current vLLM minor for the dependency vulnerabilities that flow through the Python stack.
- The Bearer token used at the reverse proxy is distinct from any participant API key, distinct from the orchestrator's other secrets, and rotated on the same cadence as other operator credentials.

## 7. Upstream references

- Ollama FAQ — [https://docs.ollama.com/faq](https://docs.ollama.com/faq) — default bind, `OLLAMA_HOST`, `OLLAMA_ORIGINS`, network exposure guidance.
- Caddy `reverse_proxy` directive — [https://caddyserver.com/docs/caddyfile/directives/reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) — full directive reference for the §4 Caddyfile example.
- nginx `ngx_http_proxy_module` — [https://nginx.org/en/docs/http/ngx_http_proxy_module.html](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) — `proxy_pass`, `auth_request`, header manipulation for the nginx variant.
- vLLM OpenAI-compatible server — [https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) — `vllm serve` overview; the CLI reference linked from that page lists `--host`, `--port`, `--api-key`.
- OWASP Top 10 for LLM Applications 2025 — [https://genai.owasp.org/llm-top-10/](https://genai.owasp.org/llm-top-10/) — LLM02 (Sensitive Information Disclosure) and LLM10 (Unbounded Consumption) frame the exposure shape of an unauthenticated local endpoint.
