"""System prompt 4-tier assembly tests."""

from __future__ import annotations

from src.prompts.tiers import assemble_prompt


def test_low_tier_contains_core_rules() -> None:
    """Low tier includes only core collaboration rules."""
    result = assemble_prompt(prompt_tier="low")
    assert "multi-model collaboration" in result
    assert "Collaboration guidelines" not in result


def test_mid_tier_adds_guidelines() -> None:
    """Mid tier adds collaboration guidelines."""
    result = assemble_prompt(prompt_tier="mid")
    assert "multi-model collaboration" in result
    assert "Collaboration guidelines" in result
    assert "Convergence awareness" not in result


def test_high_tier_adds_convergence() -> None:
    """High tier adds convergence awareness."""
    result = assemble_prompt(prompt_tier="high")
    assert "Convergence awareness" in result
    assert "Depth over brevity" not in result


def test_max_tier_includes_all() -> None:
    """Max tier includes all four deltas."""
    result = assemble_prompt(prompt_tier="max")
    assert "multi-model collaboration" in result
    assert "Collaboration guidelines" in result
    assert "Convergence awareness" in result
    assert "Depth over brevity" in result


def test_custom_prompt_appended() -> None:
    """Custom prompt is appended after tier content."""
    result = assemble_prompt(
        prompt_tier="low",
        custom_prompt="You specialize in databases.",
    )
    assert "You specialize in databases" in result
    # Custom comes after tier content
    tier_pos = result.index("multi-model")
    custom_pos = result.index("databases")
    assert custom_pos > tier_pos


def test_canary_token_embedded() -> None:
    """Assembled prompt includes a canary token."""
    result = assemble_prompt(prompt_tier="low")
    assert "CANARY_" in result


def test_unknown_tier_defaults_to_mid() -> None:
    """Unknown tier falls back to mid."""
    result = assemble_prompt(prompt_tier="unknown")
    assert "Collaboration guidelines" in result
