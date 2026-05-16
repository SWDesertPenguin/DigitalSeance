#!/usr/bin/env bash
# DigitalSeance: auto-format Python files after Claude edits them.
# Fired by PostToolUse for Edit|Write|MultiEdit. Receives event JSON on stdin.
# Failure is non-fatal — we never block the agent.

set -uo pipefail

input=$(cat)

# Extract tool_input.file_path without a JSON parser dependency.
file_path=$(echo "$input" \
  | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 \
  | sed -E 's/.*"file_path"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')

# Only act on Python files.
[[ "$file_path" == *.py ]] || exit 0

PY="/s/GitHub/DigitalSeance/.venv/Scripts/python.exe"
if [[ ! -f "$PY" ]]; then
  echo "ruff-on-save: venv python not found at $PY — skipping" >&2
  exit 0
fi

# Confirm ruff is importable; if not, surface a hint and exit clean.
if ! "$PY" -m ruff --version >/dev/null 2>&1; then
  echo "ruff-on-save: ruff not installed in venv — run 'uv pip install -e \".[dev]\"' from the project root" >&2
  exit 0
fi

"$PY" -m ruff format "$file_path" >&2 || true
"$PY" -m ruff check --fix "$file_path" >&2 || true
exit 0
