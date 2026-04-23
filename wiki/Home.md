# Digital Seance (SACP)

**Sovereign AI Collaboration Protocol** — a multi-party orchestrator where each participant brings their own model, keys, and budget; the facilitator runs the stack; humans drop in over MCP or the Web UI.

This wiki is a **short index**. Long-form specs and guides live in the main repository under [`docs/`](https://github.com/SWDesertPenguin/DigitalSeance/tree/main/docs) and change with each release.

---

## Pick a path

| If you… | Start here |
|--------|------------|
| Want the product story and repo entry | [README](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/README.md) · [Executive summary](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/SACP-Exec-Summary.md) |
| Care about *why* SACP exists and how it’s designed | **[Concepts](Concepts)** |
| Use the browser app (create session, tokens, transcript, proposals) | **[Web UI](Web-UI)** |
| Run Docker, hit Swagger, or shake down a deployment | **[Run & test](Run-and-test)** |
| Review threats, mitigations, or a real shakedown session | **[Security](Security)** |

---

## Wiki pages

- [Concepts](Concepts) — protocol principles, use cases, topologies, prompts (links into `docs/`)
- [Web UI](Web-UI) — participant / facilitator guide (links into `docs/user-guide.md`)
- [Run & test](Run-and-test) — API testing runbook + Phase 2 Web UI playbook
- [Security](Security) — attack surface analysis + sample threat-modeling transcript

---

## Contributing

Edit canonical Markdown in [`docs/`](https://github.com/SWDesertPenguin/DigitalSeance/tree/main/docs) via pull request. Use this wiki for navigation and short operator notes that don’t belong in the tree.

To update these wiki files from git: clone [`DigitalSeance.wiki`](https://github.com/SWDesertPenguin/DigitalSeance.wiki.git), copy in the `wiki/` folder from the main repo (or maintain the wiki repo directly), commit, and push.
