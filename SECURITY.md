# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in SACP, please report it responsibly. **Do not open a public issue.**

Use GitHub's private vulnerability reporting: open the **Security** tab on this repository and click **Report a vulnerability**. The report is delivered privately to the maintainers and is not publicly visible.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

You should receive a response within 72 hours.

## Scope

SACP handles API keys, auth tokens, and conversation data from multiple participants. Security issues in credential handling, authentication, encryption, or participant isolation are treated as critical.

## Supported Versions

Only the latest release on `main` receives security patches.

## Pre-push scanning (contributor workflow)

This repo uses Checkmarx 2MS (secret scanning) and KICS (IaC scanning) via a per-clone git pre-push hook. Pushes are blocked when secrets or HIGH-severity Dockerfile/compose findings appear. MEDIUM and below surface as warnings only; the threshold can be tightened locally if desired.

### Per-clone setup

The hook is not version-controlled and must be installed in each clone:

1. Install Docker Desktop and ensure it is running.
2. Pull scanner images: `docker pull checkmarx/2ms:latest && docker pull checkmarx/kics:latest`.
3. Copy the canonical `pre-push` hook into `.git/hooks/pre-push` (ask a maintainer for the current version).
4. Make it executable in Git Bash: `chmod +x .git/hooks/pre-push`.

### When the hook blocks a push

- **2MS secret finding** — if the value is real, rotate the credential and scrub history before re-pushing. If it is a documented placeholder, rewrite it to use `REPLACE_ME_BEFORE_FIRST_RUN` (or another value already on the `.2ms.yaml` allowlist) or extend the allowlist with the specific synthetic value.
- **KICS IaC finding** — fix the underlying Dockerfile or compose issue, or apply a surgical `# kics-scan ignore-line` directive when the finding is a known false positive on env-var substitution patterns.
- **Override (emergencies only)** — `git push --no-verify`. Note the reason in the next commit.
