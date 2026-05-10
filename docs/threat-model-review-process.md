# Threat-model freshness review process

> Documents the cadence, trigger conditions, and ownership for refreshing
> SACP's threat model. Implements spec 012 §FR-016. The threat model itself
> is the AI attack surface analysis listed in Constitution §13 under Security
> Analysis; this document describes when and why that artifact is reviewed
> for staleness.

**Audience**: facilitator, security-aware reviewers, contributors landing
defense-relevant changes.
**Companion docs**: the AI attack surface analysis (per Constitution §13;
the threat model under review), `docs/red-team-runbook.md` (incident catalog
feeding the review), `docs/pattern-list-update-workflow.md` (complementary
detector-side workflow).

---

## Why a review process

The threat model documents 13 attack vector families and their mitigations.
It is correct as of its last revision; it goes stale when:

- A new attack class lands that the existing 13 do not cover.
- A defense the model relies on is removed, downgraded, or made conditional.
- A participant capability arrives that broadens the attack surface (e.g.,
  topology 7 MCP-to-MCP shifts the trust boundary).
- A dependency the model assumes safe-by-construction discloses a regression.

A drift-without-review is the dangerous case: the architecture changes, the threat model does not, and the next incident hits a vector the model claims is mitigated.

---

## Cadence: per-Phase-boundary

The primary cadence is **at every Phase boundary** (Constitution §10).

- **Phase 2 -> Phase 3**: review opens when the facilitator declares the
  pre-Phase-3 audit window closed. Output: a delta block in the threat model
  documenting any vectors added, mitigations strengthened, mitigations removed,
  or vectors retired.
- **Phase 3 -> Phase 4**: review opens when Phase 3 capabilities (OAuth 2.1
  with PKCE, branching/rollback, MCP-to-MCP topology 7) are declared shipped.
- **Subsequent Phase boundaries**: same pattern.

Phase boundaries are already constitutional milestones; piggy-backing the
threat-model review on them adds no new ceremony and ensures the review
happens at the moment the architecture has just changed.

A Phase boundary review MUST produce one of:

- A no-op marker in the threat model header noting the review date and
  reviewer, with rationale ("13 vectors still cover the surface; no edits").
- A delta PR that updates the threat model and any downstream docs that
  reference its findings (cross-spec integration doc, attack-surface entries
  in spec.md files).

---

## Trigger-based review (between Phase boundaries)

Four triggers force an out-of-cycle review even when no Phase boundary is
near:

### Trigger 1 — New red-team incident category

Triggered when an entry lands in `docs/red-team-runbook.md` that does not fit
any of the existing 13 attack vectors. The pattern-list update workflow
addresses the immediate detector gap; this trigger asks whether the threat
model itself needs a new vector entry.

Example (hypothetical): the runbook adds a "convergence-detection adversarial
embedding" category. If §9 (adversarial embedding defense) already covers it,
no review needed. If it is genuinely novel, open the review.

### Trigger 2 — New participant-side capability

Triggered when a constitutional change or feature spec admits a new
participant capability that broadens the attack surface. Phase 3 brings:

- Topology 7 MCP-to-MCP — participants run their AI client-side; trust boundary
  shifts to the participant's machine.
- Branching and rollback — participants can rewrite history within a branch.
- External memory integration — orchestrator stores cross-session state.

Each of those is a trigger. Voice-mediated participants (deferred per §10)
are a trigger if and when they ever enter scope.

### Trigger 3 — Dependency major version with new attack surface

Triggered when a pinned dependency adds a new feature, transport, or
provider that the threat model has not assessed. Examples:

- LiteLLM major version adding a new provider class (new SDK shape, new
  network behavior).
- sentence-transformers major version changing the embedding family.
- A FastAPI / Starlette major version altering middleware ordering or
  WS handling.
- The MCP SDK adding new transport (e.g., HTTPS streamable replacing SSE).

A patch-level dependency bump is not a trigger by default; the SBOM + Trivy
scan handles those. The review trigger is intent-level: "did this version
change the attack surface?"

### Trigger 4 — Provider-disclosed regression

Triggered when an upstream provider (Anthropic, OpenAI, Gemini, Groq, or any
other supported provider) discloses a model-level regression that affects
defense behavior. Examples:

- A model class becomes more compliant with prompt-injection payloads it
  previously refused.
- A model's tool-call schema changes in a way that defeats existing
  spotlighting markers.
- A jailbreak technique works against the current generation that did not
  work against the prior generation.

Disclosure includes vendor blog posts, security bulletins, and known-incident
publications cited in the OSINT sources tracked per Constitution §13
(Regulatory & Frameworks).

---

## Ownership

- **Review owner**: the facilitator. The facilitator MAY delegate the review
  itself to a security-aware reviewer (per Constitution §4.7's "facilitator
  approval flow is the ultimate defense"), but the facilitator OWNs the
  decision to declare the threat model current.
- **Trigger watchers**: shared. Any contributor may file a trigger; the
  facilitator confirms whether it qualifies under one of the four categories
  above.
- **Output artifacts**: live in the threat model file itself (header date +
  reviewer initials) and, when a delta is produced, in a PR landing on
  `fix/threat-model-<phase-or-trigger-name>` per Constitution §14.2.

---

## Review checklist

When a review opens (Phase boundary or trigger), the reviewer walks this list:

1. Read the current threat model end-to-end. Note any sentence that references
   a defense the system no longer has, a Phase the system has passed, or a
   provider the system no longer supports.
2. Open `docs/red-team-runbook.md` and skim entries added since the last
   review. Confirm each maps to one of the existing 13 vectors or document a
   new one.
3. Open `docs/cross-spec-integration.md` and confirm cross-spec security
   touchpoints still match the threat model's mitigations.
4. Open the Constitution §8 (AI-specific security) and §12 validation rules
   (V10, V14, V15, V16). Confirm the threat model still cites the binding
   rules.
5. Open the spec files for any feature shipped since the last review. For
   each, confirm its Topology section (V12) and Use case section (V13) align
   with the threat model's coverage statements.
6. Produce the output artifact (no-op marker or delta PR).

---

## Out of scope for this review process

- **Per-PR threat review**. Too much overhead; the per-PR security review covers the immediate change, and the constitution + spec reviews catch architectural drift. The threat-model review is a periodic / triggered backstop, not a gate on every PR.
- **Annual cadence**. Misaligned with project pace; Phase boundaries and the
  four triggers above are the binding cadence.
- **Threat model authorship** for new specs. The spec author is responsible
  for V10-V16 compliance in their own spec; the threat-model review confirms
  the aggregate model still accommodates what was shipped, not that each spec
  drafted its own model.

---

## References

- 012 spec.md §FR-016 — the binding requirement this process implements
- 012 research.md Decision 9 — rationale for per-Phase-boundary cadence
- The AI attack surface analysis listed in Constitution §13 — the threat
  model under review
- `docs/pattern-list-update-workflow.md` — complementary detector workflow
- Constitution §8 (AI-specific security), §10 (phase boundaries),
  §12 V10-V16 (validation rules), §13 (authoritative references)
