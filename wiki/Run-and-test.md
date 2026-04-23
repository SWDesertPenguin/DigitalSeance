# Run & test

How to exercise a **live** deployment: clean database, session creation, tool/API flows, and structured Web UI shakedown.

---

## API & conversation loop

| Doc | What it covers |
|-----|----------------|
| [**SACP testing & validation runbook**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/testing-runbook.md) | Prerequisites, volume reset, `curl` flows against `:8750`, Swagger at `/docs` |

**Quick refs** (see runbook for exact commands):

- MCP / API: `http://<host>:8750` — Swagger [`/docs`](http://localhost:8750/docs) when local
- Web UI: `http://<host>:8751` — health check path in [phase2-test-playbook](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/phase2-test-playbook.md)
- Common env: `SACP_DATABASE_URL`, `SACP_ENCRYPTION_KEY` (runbook table)

---

## Web UI acceptance

| Doc | What it covers |
|-----|----------------|
| [**Phase 2 Web UI — test playbook**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/phase2-test-playbook.md) | Boot smoke, auth, user stories, XSS checks, WS expectations |

---

## Multi-LLM engineering context (optional)

| Doc | What it covers |
|-----|----------------|
| [**Eight hard problems (multi-LLM orchestrator)**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/Building_a_Multi-LLM_Orchestrator__Eight_Hard_Problems_and_How_to_Solve_Them.md) | Prompt limits, structured output, portability — background for integrators |

---

← [Home](Home) · [Concepts](Concepts) · [Web UI](Web-UI) · [Security](Security)
