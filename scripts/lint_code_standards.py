#!/usr/bin/env python3
"""Mechanical enforcement of project coding standards.

Enforces the subset of `docs/coding-standards.md` that can be checked
syntactically:

  STANDARDS — function shape rules:
    - max 25 lines per function (excluding docstring + decorators)
    - max 5 positional args (varargs/kwargs not counted)
    - type hints required on public functions (name not starting with _)
    Note: thresholds raised from 20/3 → 25/5 on 2026-04-08 based on
    shadow-mode evidence (zero new findings created at 25/5, ~30
    cleared across the touched files). See logs/lint-stats/ for the
    accumulating empirical signal.

  STANDARDS — banned functions / patterns:
    - eval(...) / exec(...)
    - pickle.load / pickle.loads
    - subprocess.* with shell=True
    - os.system(...)
    - yaml.load(...) without Loader=SafeLoader  (use yaml.safe_load)
    - import urllib / import requests  (use httpx)
    - bare `except:`
    - assert as validation (in non-test files only — assert in tests is fine)

Does NOT check:
  - hardcoded secrets (bandit's job)
  - shell quoting (shellcheck's job)
  - structured logging vs print() (style preference, file-by-file)
  - Bash scripts (shellcheck handles those)

Usage:
    python3 scripts/lint_code_standards.py path/to/file.py [more.py ...]

Exit code 0 = clean, 1 = findings, 2 = parse error.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PYTHON_RESERVED = {
    "from",
    "class",
    "def",
    "lambda",
    "import",
    "return",
    "with",
    "as",
    "if",
    "elif",
    "else",
    "for",
    "while",
    "not",
    "and",
    "or",
    "is",
    "in",
    "pass",
    "break",
    "continue",
    "try",
    "except",
    "finally",
    "raise",
    "yield",
    "global",
    "nonlocal",
    "del",
    "assert",
}

MAX_FUNCTION_LINES = 25
MAX_POSITIONAL_ARGS = 5


def _is_test_file(path: Path) -> bool:
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or "/qa/" in str(path)


def _function_body_lines(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Lines from first non-docstring statement to the end of the function."""
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return 0
    first_line = body[0].lineno
    last_line = body[-1].end_lineno or body[-1].lineno
    return last_line - first_line + 1


def _check_function_size(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, findings: list[str], path: Path
) -> None:
    # Free log lines (log.debug/info/warning/error with simple args) don't
    # count toward the size budget — see _count_free_log_lines_in_fn rationale.
    effective_lines = _function_body_lines(fn) - _count_free_log_lines_in_fn(fn)
    if effective_lines > MAX_FUNCTION_LINES:
        findings.append(
            f"{path}:{fn.lineno}: function `{fn.name}` is {effective_lines} lines "
            f"(max {MAX_FUNCTION_LINES})"
        )


def _check_arg_count(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, findings: list[str], path: Path
) -> None:
    # self/cls don't count toward the human-cognitive arg budget.
    all_pos = list(fn.args.posonlyargs) + list(fn.args.args)
    counted = [a for a in all_pos if a.arg not in {"self", "cls"}]
    if len(counted) > MAX_POSITIONAL_ARGS:
        findings.append(
            f"{path}:{fn.lineno}: function `{fn.name}` has {len(counted)} "
            f"positional args (max {MAX_POSITIONAL_ARGS})"
        )


def _check_type_hints(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, findings: list[str], path: Path
) -> None:
    # Test files are exempt — pytest test methods conventionally aren't typed.
    if fn.name.startswith("_") or _is_test_file(path):
        return
    for arg in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs):
        if arg.arg in {"self", "cls"}:
            continue
        if arg.annotation is None:
            findings.append(
                f"{path}:{fn.lineno}: public function `{fn.name}` arg `{arg.arg}` missing type hint"
            )
    if fn.returns is None and fn.name != "__init__":
        findings.append(f"{path}:{fn.lineno}: public function `{fn.name}` missing return type hint")


def _check_function_shape(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, findings: list[str], path: Path
) -> None:
    _check_function_size(fn, findings, path)
    _check_arg_count(fn, findings, path)
    _check_type_hints(fn, findings, path)


def _resolve_call_name(node: ast.Call) -> str | None:
    """Render `node.func` to a dotted name like 'subprocess.run' or 'eval'."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if not isinstance(node.func, ast.Attribute):
        return None
    parts: list[str] = []
    cur: ast.AST | None = node.func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _check_call(node: ast.Call, findings: list[str], path: Path) -> None:
    func_name = _resolve_call_name(node)
    if func_name in {"eval", "exec", "__import__", "os.system"}:
        findings.append(f"{path}:{node.lineno}: banned call `{func_name}(...)`")
    if func_name in {"pickle.load", "pickle.loads", "marshal.loads"}:
        findings.append(f"{path}:{node.lineno}: banned deserialization `{func_name}(...)`")
    if func_name == "yaml.load":
        uses_safe_loader = any(
            isinstance(kw.value, ast.Attribute | ast.Name) and ("SafeLoader" in ast.dump(kw.value))
            for kw in node.keywords
            if kw.arg == "Loader"
        )
        if not uses_safe_loader:
            findings.append(
                f"{path}:{node.lineno}: `yaml.load(...)` without SafeLoader — use yaml.safe_load"
            )
    if func_name and func_name.startswith("subprocess."):
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                findings.append(
                    f"{path}:{node.lineno}: `{func_name}(..., shell=True)` is shell-injection-prone"
                )


def _check_imports(node: ast.AST, findings: list[str], path: Path) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in {
                "urllib",
                "urllib.request",
                "requests",
                "pickle",
                "marshal",
            }:
                findings.append(
                    f"{path}:{node.lineno}: banned import `{alias.name}` (use httpx for HTTP)"
                )
    elif isinstance(node, ast.ImportFrom) and node.module in {
        "urllib",
        "urllib.request",
        "requests",
    }:
        findings.append(
            f"{path}:{node.lineno}: banned import-from `{node.module}` (use httpx for HTTP)"
        )


def _check_banned_calls(node: ast.AST, findings: list[str], path: Path, *, is_test: bool) -> None:
    if isinstance(node, ast.Call):
        _check_call(node, findings, path)
    _check_imports(node, findings, path)
    if isinstance(node, ast.ExceptHandler) and node.type is None:
        findings.append(
            f"{path}:{node.lineno}: bare `except:` catches "
            f"SystemExit/KeyboardInterrupt — use `except Exception:`"
        )
    if isinstance(node, ast.Assert) and not is_test:
        findings.append(
            f"{path}:{node.lineno}: `assert` for validation is stripped in -O "
            f"mode — use a real check + raise"
        )


# --- Telemetry helpers (Layer 1: structured stats) ---
#
# Computes per-file metrics so the linter can produce a JSONL feed for
# rule-tuning and abuse detection. The "free log line" and "abuse
# pattern" counters exist so we can experimentally evaluate the
# proposed "log.warning/error lines don't count toward the 25-line cap"
# rule without committing to it — see logs/lint-instrumentation-wip.md.

_LOG_SAFE_CALL_NAMES = {"str", "repr", "len", "int", "float", "format"}
_LOG_METHODS = {"info", "debug", "warning", "error", "critical", "exception"}


def _arg_is_log_safe(arg: ast.expr) -> bool:
    """True iff `arg` is a 'safe' AST node to appear inside a log call.

    Safe = literal / name / attribute / f-string with safe parts /
    whitelisted call (str/repr/len/int/float/format) / .get(...) call,
    recursively. Anything else (BinOp, comprehensions, lambdas, calls
    to other functions) hides logic and returns False.
    """
    if isinstance(arg, ast.Constant | ast.Name):
        return True
    if isinstance(arg, ast.Attribute):
        return _arg_is_log_safe(arg.value)
    if isinstance(arg, ast.JoinedStr):
        return all(
            _arg_is_log_safe(fv.value) for fv in arg.values if isinstance(fv, ast.FormattedValue)
        )
    if isinstance(arg, ast.Call):
        return _call_is_log_safe(arg)
    return False


def _call_is_log_safe(call: ast.Call) -> bool:
    """True iff a Call node is a whitelisted helper (str/len/.get/...) and all its args are safe."""
    func = call.func
    kw_values = [kw.value for kw in call.keywords]
    all_args_safe = all(_arg_is_log_safe(a) for a in call.args + kw_values)
    if isinstance(func, ast.Name) and func.id in _LOG_SAFE_CALL_NAMES:
        return all_args_safe
    if isinstance(func, ast.Attribute) and func.attr == "get":
        return _arg_is_log_safe(func.value) and all_args_safe
    return False


def _is_free_log_call(call: ast.Call) -> bool:
    """True iff `call` is `log.{debug,info,warning,error}(...)`.

    These are 'free lines' under the size cap because creator preference
    is 'resilient but vocal' — counting log calls toward the function-size
    budget would create pressure to strip logging from legitimately resilient
    code paths, contradicting the error-handling rule.
    """
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr in ("debug", "info", "warning", "error")
        and isinstance(f.value, ast.Name)
        and f.value.id == "log"
    )


def _stmts_excluding_docstring(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
    """Return fn.body with the leading docstring stripped, if any."""
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _count_free_log_lines_in_fn(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Sum of LINES occupied by qualifying log.{debug,info,warning,error} statements.

    A statement qualifies iff `_is_free_log_call` AND every arg passes
    `_arg_is_log_safe` (no expensive sub-calls — that's the abuse guard).
    Multi-line log calls count for their full line span so the size
    counter can subtract honestly.

    Recurses into If/Try/For/While block bodies (errors typically live
    inside conditional branches), but does NOT recurse into nested
    function/class definitions — those have their own line budget.
    Skips the leading docstring.
    """
    total = 0
    stack: list[ast.stmt] = list(_stmts_excluding_docstring(fn))
    while stack:
        stmt = stack.pop()
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            kw_values = [kw.value for kw in call.keywords]
            if _is_free_log_call(call) and all(_arg_is_log_safe(a) for a in call.args + kw_values):
                end = stmt.end_lineno or stmt.lineno
                total += end - stmt.lineno + 1
        for field_name in ("body", "orelse", "finalbody", "handlers"):
            for child in getattr(stmt, field_name, []) or []:
                if isinstance(child, ast.stmt):
                    stack.append(child)
                elif isinstance(child, ast.ExceptHandler):
                    stack.extend(child.body)
    return total


def _count_log_calls_with_fn_args(tree: ast.AST) -> int:
    """Abuse-pattern detector: count log.* calls where ANY arg fails _arg_is_log_safe.

    A spike in this count means developers are stuffing real logic into
    log call arguments to dodge a per-function line cap.
    """
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (
            isinstance(f, ast.Attribute)
            and f.attr in _LOG_METHODS
            and isinstance(f.value, ast.Name)
            and f.value.id == "log"
        ):
            continue
        kw_values = [kw.value for kw in node.keywords]
        if any(not _arg_is_log_safe(a) for a in node.args + kw_values):
            count += 1
    return count


def _count_single_call_helpers(tree: ast.AST) -> int:
    """Count private helpers (name starts with `_`, non-dunder) called from exactly one place.

    A bare-name reference (`_foo()`) counts; method calls (`x._foo()`)
    don't, because we can't statically resolve the receiver.
    """
    private_fn_names = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        and n.name.startswith("_")
        and not (n.name.startswith("__") and n.name.endswith("__"))
    }
    counts: dict[str, int] = dict.fromkeys(private_fn_names, 0)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in private_fn_names
        ):
            counts[node.func.id] += 1
    return sum(1 for c in counts.values() if c == 1)


def _length_percentiles(lengths: list[int]) -> tuple[int, int, int]:
    """Return (p50, p90, max) for a list of body line counts. (0,0,0) if empty."""
    if not lengths:
        return 0, 0, 0
    sl = sorted(lengths)
    p50 = sl[len(sl) // 2]
    p90 = sl[min(int(len(sl) * 0.9), len(sl) - 1)]
    return p50, p90, max(sl)


def _collect_function_stats(tree: ast.AST) -> dict:
    """One-pass per-file stats record. See logs/lint-instrumentation-wip.md for schema."""
    fns = [fn for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)]
    lengths = [_function_body_lines(fn) for fn in fns]
    p50, p90, lmax = _length_percentiles(lengths)
    free_logs = [_count_free_log_lines_in_fn(fn) for fn in fns]
    return {
        "n_functions": len(fns),
        "lengths_p50": p50,
        "lengths_p90": p90,
        "lengths_max": lmax,
        "free_log_lines_used": sum(free_logs),
        "free_log_lines_max_in_one_fn": max(free_logs) if free_logs else 0,
        "single_call_helpers": _count_single_call_helpers(tree),
        "log_calls_with_fn_args": _count_log_calls_with_fn_args(tree),
    }


def _emit_lint_stats(path: Path, tree: ast.AST, *, n_findings: int, output_dir: Path) -> None:
    """Append a JSONL stats record for `path` to today's file in `output_dir`."""
    now = datetime.now(UTC)
    record = {
        "ts": now.isoformat(),
        "file": str(path),
        "n_findings": n_findings,
        **_collect_function_stats(tree),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{now.date().isoformat()}.jsonl"
    with open(out_file, "a") as f:
        f.write(json.dumps(record) + "\n")


def _maybe_emit_stats(path: Path, tree: ast.AST, n_findings: int) -> None:
    """Telemetry hook — gated on env var GENNY_LINT_STATS_DIR. Never raises."""
    stats_dir = os.environ.get("GENNY_LINT_STATS_DIR")
    if not stats_dir:
        return
    try:
        _emit_lint_stats(path, tree, n_findings=n_findings, output_dir=Path(stats_dir))
    except Exception as exc:
        print(f"[stats-emit-warn] {path}: {exc}", file=sys.stderr)


def lint(path: Path) -> list[str]:
    if path.suffix != ".py":
        return []  # only Python files have an AST we can analyse
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        print(f"[parse-error] {path}: {exc}", file=sys.stderr)
        raise
    is_test = _is_test_file(path)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _check_function_shape(node, findings, path)
        _check_banned_calls(node, findings, path, is_test=is_test)
    _maybe_emit_stats(path, tree, len(findings))
    return findings


def _process_file(path: Path) -> int:
    """Lint one file and print results. Returns the per-file exit status."""
    if not path.is_file():
        print(f"[skip] not a file: {path}", file=sys.stderr)
        return 0
    try:
        findings = lint(path)
    except SyntaxError:
        return 2
    if not findings:
        print(f"{path}: ok")
        return 0
    print(f"{path}: {len(findings)} finding(s)")
    for f in findings:
        print(f"  {f}")
    return 1


# Baseline-aware mode: a finding's "identity" is its path + the message
# with line numbers and size counts normalized away. That way an
# untouched finding doesn't look "new" just because lines shifted around
# it, and a function shrinking from 90→25 lines isn't a new violation
# either — only NEW classes of finding count.

_FINDING_LINE_RE = re.compile(r"^\s*([^:]+):(\d+):\s*(.*)$")
_SIZE_RULE_RE = re.compile(r"\b(is|has)\s+(\d+)\s+(lines|positional args)\b")
_MAX_TAIL_RE = re.compile(r"\(max \d+\)")


def _normalize_finding(line: str) -> tuple[str, str, int | None] | None:
    """Return (path, fingerprint, size_value) for a finding line, or None if unparseable.

    For size-bound rules ("is N lines", "has N positional args") the captured
    N is returned as size_value and replaced with 'SIZE' in the fingerprint so
    identity is stable across the actual measurement. The (max N) tail is also
    normalized so cap-rotation doesn't invalidate the baseline. Function names
    and other identifiers are preserved verbatim, so different functions with
    the same shape don't collide.
    """
    m = _FINDING_LINE_RE.match(line)
    if not m:
        return None
    path_str, _lineno, msg = m.groups()
    size_value: int | None = None
    size_match = _SIZE_RULE_RE.search(msg)
    if size_match:
        size_value = int(size_match.group(2))
        msg = msg[: size_match.start(2)] + "SIZE" + msg[size_match.end(2) :]
    msg = _MAX_TAIL_RE.sub("(max N)", msg)
    return path_str, msg, size_value


def _load_baseline(baseline_path: Path) -> dict[tuple[str, str], int | None]:
    """Parse a saved lint output file into {(path, fingerprint): max_baseline_size}.

    For size-bound rules the value is the largest baseline size for that
    fingerprint (a current finding is grandfathered iff its size <= this).
    For non-size rules the value is None and only key membership matters.
    """
    fingerprints: dict[tuple[str, str], int | None] = {}
    for line in baseline_path.read_text().splitlines():
        norm = _normalize_finding(line)
        if norm is None:
            continue
        path_str, fp, size = norm
        key = (path_str, fp)
        prev = fingerprints.get(key)
        if size is None or prev is None:
            fingerprints[key] = size if key not in fingerprints else prev
        else:
            fingerprints[key] = max(prev, size)
    return fingerprints


def _is_grandfathered(
    norm: tuple[str, str, int | None], baseline: dict[tuple[str, str], int | None]
) -> bool:
    """A current finding passes the gate iff its (path, fingerprint) is in
    baseline AND, for size-bound rules, the current size has not grown."""
    path_str, fp, size = norm
    key = (path_str, fp)
    if key not in baseline:
        return False
    baseline_size = baseline[key]
    if size is None or baseline_size is None:
        return True
    return size <= baseline_size


def _collect_findings(paths: list[Path]) -> tuple[list[str], int]:
    """Run lint over paths, return (raw_finding_lines, parse_error_status)."""
    raw: list[str] = []
    parse_status = 0
    for path in paths:
        if not path.is_file():
            print(f"[skip] not a file: {path}", file=sys.stderr)
            continue
        try:
            findings = lint(path)
        except SyntaxError:
            parse_status = 2
            continue
        for f in findings:
            raw.append(f"  {f}")
    return raw, parse_status


def _run_baseline_mode(baseline_path: Path, paths: list[Path]) -> int:
    """Compare current lint against baseline; fail only on NEW findings.

    Scope-aware: 'cleared' is computed only against the subset of the
    baseline that covers the files we just linted, so a pre-commit run
    on a single file doesn't claim 'cleared 191 findings' just because
    it didn't visit them.
    """
    baseline = _load_baseline(baseline_path)
    raw_findings, parse_status = _collect_findings(paths)
    scanned_paths = {str(p) for p in paths if p.is_file()}
    relevant_baseline_keys = {key for key in baseline if key[0] in scanned_paths}
    current_norms = [n for f in raw_findings if (n := _normalize_finding(f)) is not None]
    current_keys = {(n[0], n[1]) for n in current_norms}
    new_findings = [
        f
        for f, n in zip(
            raw_findings,
            (_normalize_finding(f) for f in raw_findings),
            strict=True,
        )
        if n is None or not _is_grandfathered(n, baseline)
    ]
    cleared = relevant_baseline_keys - current_keys
    if cleared:
        print(f"[baseline] {len(cleared)} finding(s) cleared in scanned files — nice")
    if not new_findings:
        print(f"[baseline] no new findings vs {baseline_path}")
        return parse_status
    print(f"[baseline] {len(new_findings)} NEW finding(s) not in {baseline_path}:")
    for f in new_findings:
        print(f)
    return max(parse_status, 1)


# --- Layer 2: --analyze (read JSONL stats and print a report) ---

# Length-band thresholds for the histogram. Tune to match the proposed
# 25-line cap experiment — bands deliberately straddle the cap so we can
# see how many functions are in the danger zone.
_P90_BANDS: list[tuple[int, int, str]] = [
    (0, 10, "0-10"),
    (11, 15, "11-15"),
    (16, 20, "16-20"),
    (21, 25, "21-25"),
    (26, 30, "26-30"),
    (31, 50, "31-50"),
    (51, 10**9, "51+"),
]


def _load_jsonl_stats(stats_dir: Path) -> list[dict]:
    """Read every *.jsonl file under stats_dir into a flat list of records."""
    records: list[dict] = []
    if not stats_dir.is_dir():
        return records
    for f in sorted(stats_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _bucket_for_p90(p90: int) -> str:
    """Return the band label that contains a given p90 length."""
    for lo, hi, label in _P90_BANDS:
        if lo <= p90 <= hi:
            return label
    return "?"


def _format_p90_histogram(records: list[dict]) -> str:
    """Bucket records by lengths_p90 into the configured bands; print counts."""
    counts: Counter[str] = Counter()
    for r in records:
        counts[_bucket_for_p90(r.get("lengths_p90", 0))] += 1
    lines = ["## Function Length Histogram (p90 across all records)"]
    for _, _, label in _P90_BANDS:
        lines.append(f"  {label}: {counts.get(label, 0)}")
    return "\n".join(lines)


def _format_top_p90_files(records: list[dict], n: int = 10) -> str:
    """Top N files by their MAX p90 length across all their records."""
    by_file: dict[str, int] = {}
    for r in records:
        f = r.get("file", "?")
        by_file[f] = max(by_file.get(f, 0), r.get("lengths_p90", 0))
    top = sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)[:n]
    lines = [f"## Top {n} Files by Max p90 Length"]
    for fpath, p90 in top:
        lines.append(f"  {fpath} — p90={p90}")
    return "\n".join(lines)


def _format_free_log_section(records: list[dict]) -> str:
    """Free-log usage trend — total used, max in any one fn, fns over the cap."""
    total = sum(r.get("free_log_lines_used", 0) for r in records)
    biggest = max((r.get("free_log_lines_max_in_one_fn", 0) for r in records), default=0)
    over5 = sum(1 for r in records if r.get("free_log_lines_used", 0) > 5)
    return (
        "## Free-Log Usage\n"
        f"  Total free log lines used (sum): {total}\n"
        f"  Max in any single function: {biggest}\n"
        f"  Records where free_log_lines_used > 5: {over5}"
    )


def _format_abuse_section(records: list[dict]) -> str:
    """Abuse-pattern detector: log calls with non-whitelisted fn args."""
    by_file: dict[str, int] = {}
    for r in records:
        c = r.get("log_calls_with_fn_args", 0)
        if c > 0:
            f = r.get("file", "?")
            by_file[f] = max(by_file.get(f, 0), c)
    total = sum(by_file.values())
    lines = ["## Abuse Pattern Detector (log calls with fn args)", f"  Total: {total}"]
    if total:
        for fpath, n in sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)[:5]:
            lines.append(f"  {fpath}: {n}")
    return "\n".join(lines)


def _format_helper_density_section(records: list[dict]) -> str:
    """Single-call helper density: are we proliferating extracted-once helpers?"""
    if not records:
        return "## Single-Call Helper Density\n  (no data)"
    by_file: dict[str, int] = {}
    for r in records:
        f = r.get("file", "?")
        by_file[f] = max(by_file.get(f, 0), r.get("single_call_helpers", 0))
    files = list(by_file)
    mean = round(sum(by_file.values()) / len(files), 1) if files else 0.0
    over5 = sum(1 for v in by_file.values() if v > 5)
    return (
        "## Single-Call Helper Density\n"
        f"  Mean per file (max-snapshot): {mean}\n"
        f"  Files with > 5 single-call helpers: {over5}"
    )


def _format_lint_analysis(records: list[dict]) -> str:
    """Assemble the full multi-section report from JSONL stats."""
    if not records:
        return "No lint stats records found."
    distinct = len({r.get("file", "?") for r in records})
    sections = [
        f"## Lint Stats Summary\n  Records: {len(records)}\n  Distinct files: {distinct}",
        _format_p90_histogram(records),
        _format_top_p90_files(records),
        _format_free_log_section(records),
        _format_abuse_section(records),
        _format_helper_density_section(records),
    ]
    return "\n\n".join(sections)


# --- Layer 2b: --histogram (one-shot full-tree length distribution) ---


def _walk_python_files(root: Path) -> list[Path]:
    """Recursive .py file walk, skipping .venv and __pycache__."""
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in {".venv", "__pycache__", ".git", "node_modules"} for part in p.parts):
            continue
        out.append(p)
    return out


def _compute_full_tree_histogram(root: Path) -> str:
    """Walk root, parse every .py, bucket every function's body length."""
    bands = _P90_BANDS
    counts: Counter[str] = Counter()
    total_fns = 0
    for path in _walk_python_files(root):
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                total_fns += 1
                counts[_bucket_for_p90(_function_body_lines(node))] += 1
    lines = [f"## Full-Tree Function Length Histogram ({total_fns} functions, root={root})"]
    for _, _, label in bands:
        lines.append(f"  {label}: {counts.get(label, 0)}")
    return "\n".join(lines)


# --- Layer 4: --shadow (run lint twice with different thresholds) ---


def _pos_arg_count(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Positional arg count for a function, excluding self/cls."""
    args = list(fn.args.posonlyargs) + list(fn.args.args)
    return len([a for a in args if a.arg not in ("self", "cls")])


def _classify_fn_for_shadow(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    shadow_max_lines: int,
    shadow_max_args: int,
) -> tuple[bool, bool, bool, bool]:
    """Return (prod_long, shadow_long, prod_args, shadow_args) for one fn."""
    body_lines = _function_body_lines(fn)
    pos = _pos_arg_count(fn)
    return (
        body_lines > MAX_FUNCTION_LINES,
        body_lines > shadow_max_lines,
        pos > MAX_POSITIONAL_ARGS,
        pos > shadow_max_args,
    )


def _record_shadow_disagreement(
    path: Path,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    prod: tuple[bool, bool],
    shadow: tuple[bool, bool],
    result: dict,
) -> None:
    """Mutate result dict to record one disagreement."""
    key = (
        f"{path}:{fn.lineno}:{fn.name} "
        f"(lines={_function_body_lines(fn)}, args={_pos_arg_count(fn)})"
    )
    if prod[0] and not shadow[0]:
        result["blocked_by_prod_only"].append(f"{key} [length]")
    elif shadow[0] and not prod[0]:
        result["blocked_by_shadow_only"].append(f"{key} [length]")
    if prod[1] and not shadow[1]:
        result["blocked_by_prod_only"].append(f"{key} [args]")
    elif shadow[1] and not prod[1]:
        result["blocked_by_shadow_only"].append(f"{key} [args]")


def _shadow_scan_file(
    path: Path, shadow_max_lines: int, shadow_max_args: int, *, result: dict
) -> None:
    """Run the shadow comparison on one file, mutating `result` in place."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return
    result["files_scanned"] += 1
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        pl, sl, pa, sa = _classify_fn_for_shadow(fn, shadow_max_lines, shadow_max_args)
        if pl == sl and pa == sa:
            result["agreements"] += 1
        else:
            _record_shadow_disagreement(path, fn, prod=(pl, pa), shadow=(sl, sa), result=result)


def _run_shadow_lint(paths: list[Path], shadow_max_lines: int, shadow_max_args: int) -> dict:
    """Compare production vs shadow rules. Returns a diff dict suitable for printing."""
    result: dict = {
        "prod_max_lines": MAX_FUNCTION_LINES,
        "prod_max_args": MAX_POSITIONAL_ARGS,
        "shadow_max_lines": shadow_max_lines,
        "shadow_max_args": shadow_max_args,
        "files_scanned": 0,
        "agreements": 0,
        "blocked_by_prod_only": [],
        "blocked_by_shadow_only": [],
    }
    for path in paths:
        if path.is_file():
            _shadow_scan_file(path, shadow_max_lines, shadow_max_args, result=result)
    return result


def _format_shadow_result(result: dict) -> str:
    """Render the shadow-diff dict as a readable text report."""
    prod_lines = result["prod_max_lines"]
    prod_args = result["prod_max_args"]
    shadow_lines = result["shadow_max_lines"]
    shadow_args = result["shadow_max_args"]
    lines = [
        "## Shadow Lint Diff",
        f"  Production rules: max_lines={prod_lines}, max_args={prod_args}",
        f"  Shadow rules:     max_lines={shadow_lines}, max_args={shadow_args}",
        f"  Files scanned: {result['files_scanned']}",
        f"  Agreements: {result['agreements']}",
        f"  Blocked by PROD only ({len(result['blocked_by_prod_only'])}):",
    ]
    for s in result["blocked_by_prod_only"][:50]:
        lines.append(f"    {s}")
    lines.append(f"  Blocked by SHADOW only ({len(result['blocked_by_shadow_only'])}):")
    for s in result["blocked_by_shadow_only"][:50]:
        lines.append(f"    {s}")
    return "\n".join(lines)


def _parse_argv(argv: list[str]) -> tuple[Path | None, list[str]]:
    """Extract --baseline FILE if present, return (baseline_path, remaining_args)."""
    if len(argv) >= 2 and argv[0] == "--baseline":
        return Path(argv[1]), argv[2:]
    return None, argv


def _run_shadow_cli(argv: list[str]) -> int:
    """Parse `--shadow MAX_LINES MAX_ARGS PATH...`, run, print, return exit code."""
    if len(argv) < 4:
        print("usage: --shadow MAX_LINES MAX_ARGS PATH [PATH ...]", file=sys.stderr)
        return 2
    try:
        sml, sma = int(argv[1]), int(argv[2])
    except ValueError:
        print("error: --shadow needs integer thresholds", file=sys.stderr)
        return 2
    print(_format_shadow_result(_run_shadow_lint([Path(a) for a in argv[3:]], sml, sma)))
    return 0


def _dispatch_special_modes(argv: list[str]) -> int | None:
    """Handle --analyze / --histogram / --shadow. Return exit code or None to fall through."""
    if not argv:
        return None
    if argv[0] == "--analyze":
        if len(argv) < 2:
            print("usage: --analyze STATS_DIR", file=sys.stderr)
            return 2
        print(_format_lint_analysis(_load_jsonl_stats(Path(argv[1]))))
        return 0
    if argv[0] == "--histogram":
        root = Path(argv[1]) if len(argv) >= 2 else Path(".")
        print(_compute_full_tree_histogram(root))
        return 0
    if argv[0] == "--shadow":
        return _run_shadow_cli(argv)
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    special = _dispatch_special_modes(argv)
    if special is not None:
        return special
    baseline_path, remaining = _parse_argv(argv)
    if not remaining:
        print("error: no files to lint", file=sys.stderr)
        return 2
    if baseline_path is not None:
        return _run_baseline_mode(baseline_path, [Path(a) for a in remaining])
    exit_code = 0
    for arg in remaining:
        exit_code = max(exit_code, _process_file(Path(arg)))
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
