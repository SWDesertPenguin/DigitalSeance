# DoD Secure Development Standards — the project

Comprehensive reference for the DoD-inspired secure software development pipeline in the project. Modeled after Iron Bank / DoD secure software factories.

**Priority hierarchy:** Security > Correctness > Readability > Style

---

## Index

| # | Section |
|---|---|
| 1 | Pipeline Architecture |
| 2 | L1 — Pre-commit & Shell Hardening |
| 3 | L2 — GitLab CI Security Scanning |
| 4 | L3 — local-LLM agents Security Agents |
| 5 | Supply Chain & Iron Bank Controls |
| 6 | Kubernetes Admission (Kyverno) |
| 7 | Security Observability |
| 8 | Coding Standards & Guidelines |
| 9 | Sanitization Checkpoints |
| 10 | Status & Remaining Work |
| 11 | Banned Functions & Libraries |

---

## Pipeline Architecture

### Three-Layer Security Pipeline
Developer → [L1: pre-commit, <5s] → git push → [L2: GitLab CI, blocks merge] → deploy → [L3: local-LLM agents agents, periodic deep review]

### Design Rationale
Modeled after DoD/Iron Bank secure software factories. Three layers provide defense in depth:
- **L1 (pre-commit):** Instant developer feedback. Catches lint, SAST, formatting before code leaves the workstation. Must be <5s to avoid disrupting flow.
- **L2 (GitLab CI):** Gate before merge. Runs heavier scanning that would be too slow for pre-commit — trivy IaC scanning, semgrep custom rules, in-toto attestation. Blocks merge on failure. This is the hard gate.
- **L3 (local-LLM agents agents):** Periodic deep review by local LLM agents. Catches things static analysis misses — bash anti-patterns, SBOM CVE correlation, policy drift. Findings go to ES for triage.

### Data Flow
```
Code change
  → L1: ruff, shellcheck, yamllint, bandit (pre-commit, local, <5s)
  → git push to GitLab
  → L2: shellcheck, ruff, bandit, trivy-iac, semgrep, in-toto (CI, blocks merge)
  → Merge to main → Flux GitOps deploy (10m reconcile)
  → L3: local-LLM agents bash-audit, ci-findings-review, sbom-cve-check, policy-enforcement (periodic)
  → Findings → ES data stream logs-security.review-* → Kibana dashboard
```

### Key Files
- `.pre-commit-config.yaml` — L1 hook definitions
- `.gitlab/ci/lint.yml` — L2 CI pipeline
- `turgon/scheduler/definitions.py` — L3 local-LLM agents security schedules (4 tasks)
- `sw-standards.md` — Coding standards, injected into every agent call
- `docs/security/secure-coding-guidelines.md` — 10-section secure coding guide

### Enforcement Philosophy
- L1: Advisory (developer can technically skip with --no-verify, but this is a policy violation)
- L2: Mandatory (blocks merge, no bypass without admin override)
- L3: Informational (writes findings for human review, doesn't block anything)
- Kyverno PSS: Currently Audit mode (logs violations but doesn't reject pods). Enforce mode is the target.

---

## L1 — Pre-commit & Shell Hardening (Phases 1, 3)

### Pre-commit Hooks (.pre-commit-config.yaml)
Installed via `pre-commit install`. Runs automatically on every `git commit`.

#### Hooks configured:
| Hook | Purpose | Language |
|---|---|---|
| ruff | Python linter + formatter (replaces flake8/black/isort) | Python |
| ruff-format | Python auto-formatting | Python |
| shellcheck | Shell script static analysis | Bash/sh |
| yamllint | YAML lint | YAML |
| bandit | Python security linter (SAST) | Python |
| check-yaml | YAML syntax validation | YAML |
| check-merge-conflict | Prevents committing merge conflict markers | All |
| trailing-whitespace | Strips trailing whitespace | All |
| end-of-file-fixer | Ensures files end with newline | All |

#### Linter configs:
- `pyproject.toml` — ruff configuration (line length, import sorting, rule selection)
- `.yamllint` — yamllint rules (truthy, line-length, etc.)
- `.shellcheckrc` — shellcheck directives

### Shell Hardening (Phase 3)
All shell scripts in the project use `set -euo pipefail`:
- `-e`: Exit on error
- `-u`: Treat unset variables as errors
- `-o pipefail`: Pipeline fails if any command in pipe fails

This was applied retroactively across all existing .sh files in the repo.

### Policy
- `--no-verify` on git commit is a policy violation. Fix the hook failure, don't bypass it.
- New shell scripts MUST include `set -euo pipefail` on line 2 (after shebang).
- New Python files are auto-formatted by ruff on commit.

---

## L2 — GitLab CI Security Scanning (Phases 2, 2.5)

### CI Pipeline (.gitlab/ci/lint.yml)
Triggered on every push to GitLab. Blocks merge request approval on failure.

#### Scanning stages:
| Stage | Tool | What it checks |
|---|---|---|
| lint:shell | shellcheck | All .sh files — syntax, quoting, variable expansion |
| lint:python | ruff | All .py files — style, imports, complexity |
| sast:python | bandit | Python security issues — hardcoded secrets, SQL injection, shell injection |
| sast:iac | trivy | IaC misconfigurations in Kubernetes manifests, Helm charts, Dockerfiles |
| sast:custom | semgrep | Custom security rules from homelab/semgrep-rules (36 rules) |
| provenance | in-toto | Pipeline attestation — cryptographic proof of what ran and what it produced |

### Semgrep Custom Rules (Phase 2.5)
Repository: `homelab/semgrep-rules` on GitLab (36 rules as of 2026-04-02)

Rules cover:
- Hardcoded credentials and API keys
- Insecure cryptographic patterns
- Kubernetes security misconfigurations
- Shell injection via subprocess/os.system
- Insecure deserialization
- Missing input validation on API endpoints
- Project-specific anti-patterns

### In-toto Attestation
- Pipeline produces a signed attestation of all steps executed
- Attestation stored alongside build artifacts
- Verifiable via cosign: proves the CI pipeline actually ran (not just a manual push)
- Part of the SLSA provenance chain

### Failure Policy
- CI failure = merge blocked. No exceptions without admin override.
- False positives: add inline suppressions (`# nosec`, `# noqa`, `# semgrep-disable`) with justification comment.
- Never disable an entire rule globally without defender review.

---

## L3 — local-LLM agents Security Agents (Phase 6)

### Overview
Four security prompt templates run as scheduled local-LLM agents agent tasks. They perform deep analysis that static tools can't — reading code semantically, correlating SBOMs against CVE databases, checking policy drift.

### Security Schedules (turgon/scheduler/definitions.py)

#### 1. bash-audit
- **Schedule:** Weekly
- **What:** Reviews all .sh scripts for anti-patterns beyond what shellcheck catches — unsafe temp file creation, missing cleanup traps, race conditions, privilege escalation paths, unquoted glob expansion in loops
- **Output:** Findings written to ES `logs-security.review-*`

#### 2. ci-findings-review
- **Schedule:** Daily (after CI runs accumulate)
- **What:** Aggregates CI scan results, correlates repeat findings, identifies trends. Flags findings that have appeared 3+ times without being fixed (stale violations).
- **Output:** Summary to ES `logs-security.review-*` with severity assessment

#### 3. sbom-cve-check
- **Schedule:** Weekly (Monday, after researcher's weekly vuln report)
- **What:** Cross-references SBOM inventory at `/chonk/security/sbom/` against known CVEs from MISP/OpenCTI/NVD. Matches against actually-deployed versions (not just what's in the chart).
- **Output:** CVE matches with affected component, deployed version, fix version, CVSS score. Written to ES + the memory engine memory if critical.

#### 4. policy-enforcement-check
- **Schedule:** Weekly
- **What:** Verifies Kyverno policies are still in place and reporting correctly. Checks for pods running in violation of PSS policies (Audit mode logs). Verifies cosign image signatures on running pods. Checks SBOM freshness.
- **Output:** Policy compliance report to ES `logs-security.review-*`

### Credential Scrubbing (turgon/security/sanitizer.py)
`scrub_credentials` function — strips secrets from local-LLM agents agent outputs before they're written to ES or the memory engine. Sanitization checkpoint SAN-5 in the pipeline.

### Integration
- All findings flow to ES data stream `logs-security.review-*`
- Critical findings also written to the memory engine tagged `["defender-review"]`
- local-LLM agents agents load their role + briefing from the memory engine before executing

---

## Supply Chain & Iron Bank Controls (Phase 4)

### Iron Bank Equivalent
the project implements supply chain controls modeled after the DoD Iron Bank (Platform One's hardened container registry). These controls ensure every deployed artifact is signed, attested, and auditable.

### Container Image Signing (cosign)
- **Real cosign keypair** generated and stored securely
- **All prod images must be cosign-signed** before deployment
- **Kyverno admission policy** rejects unsigned images in all prod namespaces
- Signature verification: `cosign verify --key <public-key> <image>`

### SBOM (Software Bill of Materials)
- **Format:** CycloneDX (industry standard, machine-readable)
- **Generation:** Produced for every release/build
- **Storage:** `/chonk/security/sbom/` with 2-year retention
- **Consumption:** local-LLM agents `sbom-cve-check` task cross-references against CVE databases weekly
- Every deployed service should have a current SBOM on file

### SLSA Provenance (in-toto)
- **Pipeline attestation** via `cosign attest` using in-toto predicate format
- **What it proves:** Which CI steps ran, what inputs they consumed, what outputs they produced
- **Verification:** `cosign verify-attestation` confirms the artifact went through the full pipeline
- **Level:** Targets SLSA Level 2 (authenticated build service, version-controlled build process)

### Dependency Management
- **Vendoring:** `pip-compile --generate-hashes` produces pinned requirements with SHA256 verification
- **Pre-scanning:** Dependencies scanned before inclusion (bandit + safety)
- **No floating versions:** All deps pinned to exact versions with hashes
- **Update process:** Bump version → regenerate hashes → CI validates → merge

### Pipeline Integrity Monitoring
- **SHA256 hashes** of critical pipeline files stored in Vault
- **local-LLM agents weekly verify:** Compares current pipeline file hashes against Vault reference
- **Drift detection:** If pipeline files change without a corresponding Vault update, it's flagged

### Git SSH Signing
- Commits signed with SSH keys (not GPG)
- Verifiable via `git log --show-signature`

---

## Kubernetes Admission — Kyverno (Phase 5)

### Overview
5 Kyverno Pod Security Standard (PSS) policies deployed in **Audit mode** across all prod namespaces. These enforce baseline security constraints on pod specifications.

### Policies

#### 1. require-resource-limits
- **What:** Every container must specify CPU and memory requests/limits
- **Why:** Prevents noisy-neighbor resource starvation, enables capacity planning
- **Fields:** `resources.requests.cpu`, `resources.requests.memory`, `resources.limits.cpu`, `resources.limits.memory`

#### 2. require-read-only-root
- **What:** Container root filesystem must be read-only (`readOnlyRootFilesystem: true`)
- **Why:** Prevents runtime filesystem tampering, forces explicit volume mounts for writable paths
- **Workaround:** Use emptyDir volumes for /tmp, /var/run, etc.

#### 3. require-non-root
- **What:** Containers must run as non-root (`runAsNonRoot: true`, `runAsUser` > 0)
- **Why:** Limits blast radius of container escape
- **Fields:** `securityContext.runAsNonRoot`, `securityContext.runAsUser`

#### 4. disallow-privileged
- **What:** No privileged containers (`privileged: false`), no host namespaces, no host ports
- **Why:** Privileged containers have full host access — equivalent to root on the node
- **Fields:** `securityContext.privileged`, `hostNetwork`, `hostPID`, `hostIPC`, `hostPorts`

#### 5. require-probes
- **What:** Every container must define readiness and liveness probes
- **Why:** Kubernetes can't properly manage pod lifecycle without health signals
- **Fields:** `readinessProbe`, `livenessProbe`

### Current State: Audit Mode
- Policies **log violations** but do **not reject pods**
- Violations visible in: `kubectl get policyreport -A`, Kyverno logs, ES security indices
- Existing workloads may have violations that need remediation before switching to Enforce

### Enforcement Roadmap
1. Remediate existing violations (some charts need securityContext additions)
2. Switch individual policies to Enforce one at a time (least disruptive first)
3. Target: all 5 policies in Enforce mode
4. Defender role monitors violation reports and advocates for Enforce timeline

---

## Security Observability (Phase 5.5)

### ES Data Stream: logs-security.review-*
Central aggregation point for all security pipeline findings across L2 and L3.

### Data Stream Details
- **Name:** `logs-security.review-default`
- **Type:** Data stream (time-series, append-only, ILM-managed)
- **Status:** LIVE as of 2026-04-02

### ILM Policy
- Hot tier: 7 days (active writes, local-path PVC)
- Warm tier: 30 days (NFS, read-only)
- Delete: 90 days
- Rollover: 50GB or 7 days, whichever comes first

### Ingest Pipeline
- Normalizes findings from different sources (CI, local-LLM agents, manual) into common schema
- Adds `@timestamp`, `source` (ci/turgon/manual), `severity`, `rule_id`, `file_path`, `finding`
- Strips sensitive content before indexing

### What flows here:
| Source | Findings |
|---|---|
| GitLab CI (L2) | bandit, shellcheck, trivy, semgrep violations that passed merge |
| local-LLM agents bash-audit (L3) | Shell anti-patterns, unsafe patterns |
| local-LLM agents ci-findings-review (L3) | Stale/repeat CI violations |
| local-LLM agents sbom-cve-check (L3) | SBOM-to-CVE matches |
| local-LLM agents policy-enforcement (L3) | Kyverno violations, unsigned images, stale SBOMs |

### Kibana Dashboard Schema
- Dashboard planned (schema defined, not yet built)
- Views: findings by severity, by source, by file, trend over time
- Filters: date range, source, severity, rule_id

### Querying
```
GET logs-security.review-*/_search
{ "query": { "range": { "@timestamp": { "gte": "now-7d" } } }, "sort": [{ "@timestamp": "desc" }] }
```

local-LLM agents defender role includes rule to check this data stream during SIEM reviews.

---

## Coding Standards & Guidelines (Phases 0, 7)

### sw-standards.md (Project Root)
Master coding standards file. Injected into every agent call via CLAUDE.md or role context. Derived from Clean Code (Robert C. Martin), DevOps (DORA/Accelerate), Lean (Poppendieck), and NIST SSDF.

**Priority hierarchy:** Security > Correctness > Readability > Style

### Clean Code Standards
- KISS. One function = one thing. Max 25 lines (excluding pure log.debug/info/warning/error lines), max 5 positional args.
  - Rule rotated 2026-04-08 from 20/3 → 25/5 + free log lines. Empirical basis: local_genny shadow-mode lint experiment (logs/lint-stats/) showed ~30 findings cleared, 0 new findings, no measurable quality regression. The "free log lines" carve-out exists because counting log.{debug,info,warning,error} toward the cap creates pressure to STRIP logging in long-but-legitimate functions, which contradicts the creator's resilient-but-vocal error handling rule.
- Descriptive names. No encodings. Declare variables near use.
- Boy Scout Rule: leave code cleaner than you found it.
- Polymorphism over conditionals. Dependency injection. Law of Demeter.
- Exceptions over error codes. Don't return/pass null. Provide context.
- Creator's rule: resilient but vocal — retry transient, log retries, fail loud on unrecoverable.
- Never swallow exceptions. Never use bare except.
- Validate ALL external inputs. Parameterize queries. Sanitize output.
- Encrypt at rest + TLS in transit. Audit trail for privileged operations.

### DevOps Standards
- Trunk-based development. Automated build+test on commit.
- Pipeline: lint → SAST → unit → integration. Target <15min.
- All infra version-controlled. Declarative. Immutable. Zero-downtime deploys.
- SBOM for every release. Code signing. Strict env separation. Reproducible builds.

### Lean Standards
- Eliminate waste. Small batches. Pull systems.
- Defer commitment: last responsible moment, preserve options.
- Build quality in: prevent defects, automate checks.

### Language Conventions
**Python:** type hints on all public functions, dataclasses for data, pathlib for paths, f-strings for formatting, httpx for HTTP.

**Bash:** set -euo pipefail, quote all variables, use functions, trap cleanup EXIT.

### docs/security/secure-coding-guidelines.md (Phase 7)
10-section secure coding guide with enforcement matrix.

#### Sections:
1. **Input Validation** — validate all external inputs, whitelist over blacklist
2. **Output Encoding** — context-aware encoding (HTML, SQL, shell, LDAP)
3. **Authentication** — no plaintext passwords, MFA, session management
4. **Authorization** — principle of least privilege, RBAC, deny by default
5. **Cryptography** — no custom crypto, use established libraries, key rotation
6. **Error Handling** — no stack traces in production, structured error responses
7. **Logging** — structured, no sensitive data in logs, audit trail for privileged ops
8. **Data Protection** — encrypt at rest + transit, minimize data collection, retention limits
9. **Dependency Management** — pin versions, hash verification, regular audit
10. **API Security** — rate limiting, input validation, authentication on all endpoints

#### Enforcement Matrix
Maps each section to which pipeline layer enforces it:
- **L1 (pre-commit):** Catches formatting, basic SAST (bandit), lint
- **L2 (CI):** Catches deeper SAST (semgrep custom rules), IaC misconfig (trivy)
- **L3 (local-LLM agents):** Catches semantic issues, policy drift, CVE correlation
- **Manual review:** Architecture decisions, threat modeling, access control design

### Reference Implementation: healthcheck-api (Phase 0)
FastAPI reference app demonstrating all standards in practice:
- 27 tests, 99% coverage
- Proper error handling, input validation, structured logging
- Demonstrates the "right way" for new services in the stack

---

## Sanitization Checkpoints (SAN-1 through SAN-8)

### Overview
8 checkpoints where data is scrubbed for credentials, PII, and sensitive content before crossing a trust boundary. Each checkpoint has a designated owner and enforcement mechanism.

### Checkpoints

#### SAN-1: Pre-commit
- **Where:** Developer workstation, before git commit
- **What:** Hooks check for hardcoded secrets (bandit B105/B106/B107, regex patterns)
- **Owner:** Developer (L1)

#### SAN-2: CI Pipeline
- **Where:** GitLab CI, during lint.yml execution
- **What:** Bandit SAST + semgrep custom credential rules scan all staged code
- **Owner:** CI pipeline (L2)

#### SAN-3: Container Build
- **Where:** Docker build process
- **What:** Trivy scans built image for embedded secrets, Dockerfile best practices
- **Owner:** CI pipeline (L2)

#### SAN-4: Kubernetes Admission
- **Where:** Kyverno admission controller
- **What:** Validates pod specs don't mount host secrets, use privileged mode, or expose host network
- **Owner:** Kyverno (cluster admission)

#### SAN-5: local-LLM agents Agent Output
- **Where:** local-LLM agents agent → ES/the memory engine write path
- **What:** `scrub_credentials` (turgon/security/sanitizer.py) strips secrets from agent outputs before storage
- **Owner:** local-LLM agents runtime (L3)

#### SAN-6: the memory engine Write Gate
- **Where:** the memory engine MCP server, on remember/anchor
- **What:** Prompt injection detection + credential pattern matching on incoming memories
- **Owner:** the memory engine server

#### SAN-7: the memory engine Enrichment
- **Where:** the memory engine enrichment pipeline (doc2query)
- **What:** Enriched content inherits redaction markers from source content
- **Owner:** the memory engine consolidation daemon

#### SAN-8: Log Shipping
- **Where:** local-LLM agents logging/shipper.py → ES
- **What:** Log output sanitized before shipping to Elasticsearch
- **Owner:** local-LLM agents logging subsystem

### Verification
- local-LLM agents `policy-enforcement-check` task verifies SAN checkpoints are active weekly
- Vale credential sweep on every wake catches anything that slipped through
- groom_content_scan provides regex-based audit across all stored memories

---

## Status & Remaining Work

### Current Status (as of 2026-04-02)
**Phases 0-7: COMPLETE.** Phase 8: PARTIAL.

### Phase 8 Completion Status
| Sub-phase | Description | Status |
|---|---|---|
| 8a | Vendored deps + credential scrubbing | DONE |
| 8b | seccomp profiles | REMAINING |
| 8c | AppArmor profiles | REMAINING |
| 8d | Falco runtime security | REMAINING |
| 8e | ES watchers (alerting on security findings) | REMAINING |
| 8f | helm-sast (Helm chart security scanning) | DONE |
| 8g | Pipeline integrity monitoring | DONE |
| 8h | Signed git tags | DONE |
| 8i | Dynamic secrets (Vault dynamic DB credentials) | REMAINING |
| 8j | Auto-rotation (automated secret rotation) | DONE |
| 8k | (completed, details in execution status) | DONE |
| 8l | MR-only workflow (no direct push to main) | DONE |

### What's Live
- Pre-commit hooks: active on all repos
- GitLab CI lint.yml: running on push
- Semgrep rules: 36 custom rules on GitLab (homelab/semgrep-rules)
- Kyverno: 5 PSS policies in Audit mode
- Cosign: images signed, Kyverno admission active
- ES data stream: logs-security.review-default LIVE
- local-LLM agents security tasks: 4 schedules active
- Tests: 56+14 passing on ai-node (local-LLM agents test suite)

### Remaining Work (Phase 8 gaps)
1. **seccomp profiles (8b):** Custom seccomp profiles for high-risk containers. Needs profiling of syscall usage per pod, then writing allow-list profiles.
2. **AppArmor profiles (8c):** Mandatory access control profiles for containers. Similar approach to seccomp — profile first, then restrict.
3. **Falco runtime security (8d):** Real-time syscall monitoring + alerting. Falco deployment to k3s, custom rules for the project-specific threat patterns, integration with ES alerting.
4. **ES watchers/alerting (8e):** Elasticsearch watcher queries that trigger alerts on security findings in logs-security.review-*. Needed to close the loop — findings exist but nobody gets paged.
5. **Dynamic secrets (8i):** Vault dynamic database credentials (short-lived, auto-rotated). Currently using static secrets with VSO rotation — dynamic credentials are the next step.

### Priority for Remaining Work
1. ES watchers (8e) — highest impact, closes the alerting gap
2. Falco (8d) — runtime visibility is a significant defense layer
3. Dynamic secrets (8i) — reduces credential exposure window
4. seccomp (8b) / AppArmor (8c) — container hardening, lower priority until Kyverno moves to Enforce

---

## Banned Functions & Libraries

NEVER use these — they are security violations.

### Python BANNED
- `eval()`, `exec()` — arbitrary code execution
- `pickle.loads/load()` — deserialization RCE
- `subprocess(shell=True)`, `os.system()` — shell injection
- `yaml.load()` without `Loader=SafeLoader` — object instantiation
- `marshal.loads()` — unsafe deserialization
- `__import__()` — dynamic import
- `urllib`, `requests` — use httpx (better defaults, TLS verification)
- Bare `except:` — catches SystemExit/KeyboardInterrupt
- `assert` for validation — stripped in -O mode
- Hardcoded passwords/tokens/secrets in source

### Bash BANNED
- Scripts without `set -euo pipefail`
- Unquoted variables (`$var` → `"$var"`)
- `eval` in shell
- `curl | bash` patterns
- Temp files without `mktemp`
- Missing `trap cleanup EXIT`

### DevOps Awareness
- Structured logging (no print()). Distributed tracing where applicable.
- All infra version-controlled. Declarative preferred. Immutable.
- SBOM awareness. Pin dependencies. Hash verification.
