# Web UI

End-user behavior for the Phase 2 SPA (session creation, auth, transcript, participants, review gate, proposals, facilitator admin). **Source of truth** is the draft guide in the main repo.

---

## Primary guide

| Doc | Audience |
|-----|----------|
| [**SACP Web UI — user guide**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/user-guide.md) | Participants and facilitators using the browser |

> The guide is marked **DRAFT / WIP** in-repo. Prefer that file for screenshots and step-by-step UI detail as the product evolves.

---

## Operator shakedown (acceptance)

| Doc | Audience |
|-----|----------|
| [**Phase 2 Web UI — test playbook**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/phase2-test-playbook.md) | Operators validating Web UI + security controls before production |

Typical stack: MCP **8750**, Web UI **8751**; see playbook for env vars (`SACP_WEB_UI_ALLOWED_ORIGINS`, `SACP_WEB_UI_MCP_ORIGIN`).

---

← [Home](Home) · [Concepts](Concepts) · [Run & test](Run-and-test) · [Security](Security)
