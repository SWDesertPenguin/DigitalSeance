# Security

SACP’s **AI-to-AI loop** means one participant’s model output becomes another’s input — a distinct trust and abuse surface. Canonical analysis and a real session example live in the repo.

---

## Threat catalog & mitigations

| Doc | What it covers |
|-----|----------------|
| [**AI attack surface analysis (SACP orchestrator)**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/AI_attack_surface_analysis_for_SACP_orchestrator.md) | Vector families, severity, mitigations, standards mappings |

Use this for security reviews, hardening priorities, and alignment with implementation (sanitization, spotlighting, rate limits, prompt tiers, etc.).

---

## Worked example (transcript)

| Doc | What it covers |
|-----|----------------|
| [**Shakedown test: threat modeling session**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/sacp-shakedown-threat-model-session.md) | Full-session transcript + executive summary (illustrative quality and spend) |

---

## Design cross-links

- High-level architecture and trust boundaries: [**sacp-design.md**](https://github.com/SWDesertPenguin/DigitalSeance/blob/main/docs/sacp-design.md)
- Data-classification / policy drafts may live under [`.specify/memory/`](https://github.com/SWDesertPenguin/DigitalSeance/tree/main/.specify/memory) — confirm path in-repo when citing.

---

← [Home](Home) · [Concepts](Concepts) · [Web UI](Web-UI) · [Run & test](Run-and-test)
