#!/usr/bin/env python3
"""Compute the canonical sha256 hash of a message-list JSON for mock fixtures.

Reads a JSON message list from stdin, computes
`sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False))` per
spec 020 research.md §8, and prints the hex digest.

Usage:
    cat msgs.json | python scripts/compute_mock_fixture_hash.py
"""

from __future__ import annotations

import hashlib
import json
import sys


def main() -> int:
    raw = sys.stdin.read()
    try:
        messages = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    if not isinstance(messages, list):
        print("stdin must contain a JSON list of messages", file=sys.stderr)
        return 2
    canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    print(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
