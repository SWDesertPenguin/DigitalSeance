# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for PKCE S256 primitives. Spec 030 Phase 4 FR-071."""

from __future__ import annotations

from src.mcp_protocol.auth.pkce import compute_challenge, generate_code_verifier, verify_challenge


def test_s256_round_trip() -> None:
    verifier = generate_code_verifier()
    challenge = compute_challenge(verifier)
    assert verify_challenge(verifier, challenge) is True


def test_plain_method_rejected() -> None:
    verifier = generate_code_verifier()
    assert not verify_challenge(verifier, verifier)


def test_verifier_mismatch_returns_false() -> None:
    v1 = generate_code_verifier()
    v2 = generate_code_verifier()
    challenge = compute_challenge(v1)
    assert verify_challenge(v2, challenge) is False


def test_verifier_length() -> None:
    verifier = generate_code_verifier()
    assert len(verifier) >= 43
