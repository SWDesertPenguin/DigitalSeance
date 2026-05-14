# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 028 §FR-019 — architectural test for visibility-filter bypass paths.

AST-scans ``src/`` for ``messages.content`` read sites and asserts every
hit lands on the explicit allowlist below. Every entry on the allowlist
carries a documented rationale; new entries require this test file to
be edited, which forces a reviewer to consider whether the new read
site is dispatch-path (must apply ``_filter_visibility``) or read-API
(must apply its own visibility-aware projection).

Per spec 028 research.md §4 + §13 the test mirrors the cheap-enforcement
pattern: AST precision over grep false-positives, single-file
allowlist for reviewable drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


# Files allowed to read ``messages.content`` directly.
#
# Each entry maps the relative path to a one-line rationale. Adding a new
# entry IS the review surface — the diff lands the rationale alongside
# the access. Removals require confirming the file no longer touches
# message content (e.g., refactored to take a sanitized payload).
_ALLOWLIST: dict[str, str] = {
    # Dispatch path (applies _filter_visibility internally).
    "orchestrator/context.py": "assembler — runs _filter_visibility on message load",
    # Visibility-aware spec 005 surface.
    "orchestrator/summarizer.py": "summarizer — two-tier emission per FR-018",
    # Loop reads its own (CAPCOM's) outgoing turn before persist; not cross-participant.
    "orchestrator/loop.py": "turn loop — assembled context (post-filter) or speaker's own turn",
    "orchestrator/announcements.py": "facilitator announcements — public-scope by construction",
    # Provider boundary works on ContextMessage (already filtered upstream).
    "api_bridge/format.py": "provider-format adapter — consumes ContextMessage",
    # Facilitator-only read APIs (visibility-aware via spec 028 FR-024).
    "participant_api/tools/debug.py": "spec 010 debug export — emits visibility_partition (FR-024)",
    "participant_api/tools/session.py": "facilitator session tools — md/JSON export rendering",
    # Self-scoped read API. Transcript-API visibility filter is a tracked follow-up.
    "participant_api/tools/participant.py": "participant /history — caller-scoped read",
    # Web UI state_snapshot — primary consumer is the human SPA.
    "web_ui/snapshot.py": "state_snapshot for the Web UI — human consumer",
    # AST disambiguation incidentals (kept for defense-in-depth).
    "web_ui/proxy.py": "HTTP proxy — upstream.content is the response body, not a Message",
    "api_bridge/litellm/dispatch.py": "provider response — choice.message.content from the LLM",
}


# Attribute names that indicate the read is on a Message-shaped object.
_MESSAGE_LIKE_NAMES = frozenset({"msg", "message", "m", "row"})


def _iter_python_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def _reads_message_content(node: ast.AST) -> bool:
    """True when ``node`` is ``<name>.content`` and the name is Message-shaped."""
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "content":
        return False
    if not isinstance(node.value, ast.Name):
        return False
    return node.value.id in _MESSAGE_LIKE_NAMES


def _files_with_message_content_reads() -> set[str]:
    """Walk src/, return relative paths whose AST contains a Message.content read."""
    hits: set[str] = set()
    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if _reads_message_content(node):
                rel = path.relative_to(SRC).as_posix()
                hits.add(rel)
                break
    return hits


def test_no_unallowlisted_message_content_reads():
    """FR-019 — every src/ file that reads ``messages.content`` is allowlisted."""
    hits = _files_with_message_content_reads()
    unexpected = sorted(hits - _ALLOWLIST.keys())
    assert not unexpected, (
        "Spec 028 FR-019: the following src/ files read messages.content but "
        "are not on the allowlist. Either route the read through "
        "ContextAssembler._filter_visibility, OR add an entry with a "
        "rationale to _ALLOWLIST in tests/test_028_architectural.py:\n  " + "\n  ".join(unexpected)
    )


def test_allowlist_entries_actually_exist():
    """Allowlist drift guard — entries pointing at vanished files fail."""
    missing = sorted(rel for rel in _ALLOWLIST if not (SRC / rel).exists())
    assert not missing, (
        "Spec 028 FR-019 allowlist references files that no longer exist:\n  "
        + "\n  ".join(missing)
    )


def test_allowlist_rationales_are_non_empty():
    """Every allowlist entry carries a one-line rationale string."""
    blank = sorted(rel for rel, reason in _ALLOWLIST.items() if not reason.strip())
    assert not blank, "Spec 028 FR-019 allowlist entries with empty rationales:\n  " + "\n  ".join(
        blank
    )
