# SPDX-License-Identifier: AGPL-3.0-or-later

"""Corpus-fixture sanity tests (spec 012 FR-001 / FR-002).

Verifies tests/fixtures/{benign,adversarial}_corpus.txt have the shape
downstream consumers expect (007 sanitizer regression, 007 §FR-019 FPR
measurement, 007 §FR-021 perf baseline) and that representative
adversarial samples actually trigger their corresponding detectors —
proves the corpora are wired and consumable end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from src.security.exfiltration import filter_exfiltration
from src.security.jailbreak import check_jailbreak
from src.security.sanitizer import sanitize

REPO_ROOT = Path(__file__).resolve().parent.parent
BENIGN = REPO_ROOT / "tests" / "fixtures" / "benign_corpus.txt"
ADVERSARIAL = REPO_ROOT / "tests" / "fixtures" / "adversarial_corpus.txt"

_BENIGN_CATEGORIES = {
    "collaboration-prose",
    "technical-prose",
    "code-discussion",
    "credential-placeholders",
    "pure-script-non-latin",
    "markdown-without-images",
    "html-without-src",
}

_ADVERSARIAL_CATEGORIES = {
    "cyrillic-homoglyph",
    "chatml-tokens",
    "role-markers",
    "llama-markers",
    "html-comments",
    "override-phrases",
    "new-instructions-phrases",
    "from-now-on",
    "openai-credentials",
    "anthropic-credentials",
    "gemini-credentials",
    "groq-credentials",
    "jwt-credentials",
    "fernet-credentials",
    "markdown-images",
    "html-src",
    "data-urls",
    "jailbreak-phrases",
}


def _parse_categories(path: Path) -> dict[str, list[str]]:
    """Return {category: [non-comment non-blank lines]}."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("# CATEGORY:"):
            current = line.split(":", 1)[1].strip()
            sections[current] = []
            continue
        if not line or line.startswith("#"):
            continue
        if current is not None:
            sections[current].append(raw)
    return sections


def test_benign_corpus_has_expected_categories():
    sections = _parse_categories(BENIGN)
    assert set(sections) == _BENIGN_CATEGORIES, (
        f"benign corpus categories drift: have {sorted(sections)}, "
        f"expected {sorted(_BENIGN_CATEGORIES)}"
    )
    for cat, lines in sections.items():
        assert lines, f"benign corpus category '{cat}' has no samples"


def test_adversarial_corpus_has_expected_categories():
    sections = _parse_categories(ADVERSARIAL)
    assert set(sections) == _ADVERSARIAL_CATEGORIES, (
        f"adversarial corpus categories drift: have {sorted(sections)}, "
        f"expected {sorted(_ADVERSARIAL_CATEGORIES)}"
    )
    for cat, lines in sections.items():
        assert lines, f"adversarial corpus category '{cat}' has no samples"


def _sanitizer_modifies(samples: list[str]) -> bool:
    """Sanitizer should change at least one sample (any pattern hit)."""
    return any(sanitize(s) != s for s in samples)


def _exfil_flags(samples: list[str]) -> bool:
    """Exfiltration filter should flag at least one sample."""
    return any(bool(filter_exfiltration(s)[1]) for s in samples)


def _jailbreak_flags(samples: list[str]) -> bool:
    """Jailbreak detector should flag at least one sample."""
    return any(check_jailbreak(s).flagged for s in samples)


_SANITIZER_CATEGORIES = {
    "cyrillic-homoglyph",
    "chatml-tokens",
    "role-markers",
    "llama-markers",
    "html-comments",
    "override-phrases",
    "new-instructions-phrases",
    "from-now-on",
}

_EXFIL_CATEGORIES = {
    "openai-credentials",
    "anthropic-credentials",
    "gemini-credentials",
    "groq-credentials",
    "jwt-credentials",
    "fernet-credentials",
    "markdown-images",
    "html-src",
}

_JAILBREAK_CATEGORIES = {"jailbreak-phrases"}


def test_sanitizer_categories_trigger_sanitizer():
    sections = _parse_categories(ADVERSARIAL)
    for cat in _SANITIZER_CATEGORIES:
        assert _sanitizer_modifies(
            sections[cat]
        ), f"sanitizer did not modify any sample in adversarial category '{cat}'"


def test_exfil_categories_trigger_exfiltration_filter():
    sections = _parse_categories(ADVERSARIAL)
    for cat in _EXFIL_CATEGORIES:
        assert _exfil_flags(
            sections[cat]
        ), f"exfiltration filter did not flag any sample in adversarial category '{cat}'"


def test_jailbreak_categories_trigger_jailbreak_detector():
    sections = _parse_categories(ADVERSARIAL)
    for cat in _JAILBREAK_CATEGORIES:
        assert _jailbreak_flags(
            sections[cat]
        ), f"jailbreak detector did not flag any sample in adversarial category '{cat}'"


def _all_lines(sections: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [(cat, line) for cat, lines in sections.items() for line in lines]


def test_benign_corpus_zero_fpr_against_pipeline():
    """Hand-curated benign samples MUST NOT trigger any detector.

    This is a strict 0% FPR guard for THIS specific corpus, not the
    007 §FR-019 advisory targets (which apply to a representative
    real-world distribution). If a benign sample starts triggering,
    fix the sample — don't relax the guard.
    """
    sections = _parse_categories(BENIGN)
    failures: list[str] = []
    for cat, line in _all_lines(sections):
        if sanitize(line) != line:
            failures.append(f"{cat}: sanitizer modified: {line!r}")
        if filter_exfiltration(line)[1]:
            flags = filter_exfiltration(line)[1]
            failures.append(f"{cat}: exfiltration flagged {flags}: {line!r}")
        if check_jailbreak(line).flagged:
            reasons = check_jailbreak(line).reasons
            failures.append(f"{cat}: jailbreak flagged {reasons}: {line!r}")
    assert not failures, "\n".join(failures)
