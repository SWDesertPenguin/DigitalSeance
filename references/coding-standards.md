# Angrist coding standards

The mechanical rules below are enforced by
`scripts/lint_code_standards.py` (baseline-aware) and wired into
`.pre-commit-config.yaml`. They mirror the standards rotation that
the local_genny project landed on 2026-04-08, lifted into angrist
verbatim because the same rationale applies.

## Function shape

- **≤25 lines per function**, excluding docstrings and decorators.
- **≤5 positional arguments.** Anything past five must be keyword-only
  (use `*,` separator). Variadic `*args` / `**kwargs` don't count.
- **Type hints required on public functions** (any function whose name
  doesn't start with `_`).
- **Caller above callee.** Orchestrator first, helpers below it. Read
  top-down.

### Free log lines exception

`log.{debug,info,warning,error}(...)` calls do not count toward the
25-line cap. Rationale: the "resilient but vocal" rule (every error
path must log) and the "small functions" rule (≤25 lines) pull in
opposite directions for any function that legitimately needs
observability. Exempting log lines lets both rules coexist without
either being watered down.

This exemption is scoped narrowly:
- Only the four canonical log levels.
- Only on a `log` name (the conventional module logger).
- Multi-line log calls have their full line span subtracted.

Anything else — `print`, `logger.info`, `self.log.info`, raised
exceptions, comments — counts normally.

## Banned calls / patterns

- `eval(...)`, `exec(...)`
- `pickle.load`, `pickle.loads`
- `subprocess.*` with `shell=True`
- `os.system(...)`
- `yaml.load(...)` without `Loader=SafeLoader` (use `yaml.safe_load`)
- `import urllib`, `import requests` (use `httpx`)
- Bare `except:`
- `assert` as validation in non-test files

The linter does not check secrets (gitleaks does), shell quoting
(shellcheck), or print-vs-structured-logging style.

## Decomposition guidance

- **Frozen dataclass carriers** when state threads through 3+
  helpers and the arg list grows past 5. Bundle into one
  `@dataclass(frozen=True)` and pass that. The `_ShipperState`,
  `_AgenticState`, and `_SubagentLoopState` patterns from local_genny
  are good models.
- **Resilient but vocal.** Never silently swallow exceptions. Every
  caught exception logs at WARN or ERROR with enough context to
  reproduce. The free-log-lines exemption exists to make this cheap.
- **Hoist constants out of functions.** A 50-line function whose
  body is mostly a static dict literal should be a module-level
  constant + a 3-line accessor. The honeypot decoy specs in
  local_genny are the canonical example.

## Baseline mode

The linter ships with a frozen baseline at
`logs/standards-baseline/2026-04-08_baseline-25-5.txt` capturing the
161 findings present at port time. Pre-commit runs in
`--baseline` mode: it fails on **new** findings only, not on the
existing backlog.

Workflow for grinding the baseline down:

1. Pick a hotspot (start with the largest functions).
2. Refactor until `python scripts/lint_code_standards.py <files>`
   runs clean against just those files.
3. Run the full `--baseline` pass — pre-commit shows
   `[baseline] N finding(s) cleared`.
4. When a file is fully clean, drop its lines from the baseline file.

Targets land at zero. The baseline is a temporary scaffold, not a
permanent allow-list.

## Why these specific numbers (25/5)

The rotation was 20/3 → 25/5 + free-log-lines after empirical
analysis on the local_genny tree showed that 20/3 was thrashing on
small, correct functions (mostly tool registration boilerplate and
log-heavy error paths). The 25/5 rotation cleared ~30 false-positive
findings without unmasking any real complexity offenders, and the
free-log-lines exemption stripped another 10 from the same set. See
the local_genny standards retrofit (commits 2de841c → 4be1da9) for
the empirical record.

## Known divergences from local_genny

None today. If a divergence becomes necessary it should be documented
here with the rationale, not silently introduced into the linter.
