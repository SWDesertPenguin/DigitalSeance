"""Unit tests for sliding-window turn cap (SACP_CONTEXT_MAX_TURNS)."""

from __future__ import annotations

from src.orchestrator.context import MVC_FLOOR_TURNS, _history_turns


def test_defaults_when_env_absent(monkeypatch):
    monkeypatch.delenv("SACP_CONTEXT_MAX_TURNS", raising=False)
    assert _history_turns() == 20


def test_reads_env_override(monkeypatch):
    monkeypatch.setenv("SACP_CONTEXT_MAX_TURNS", "12")
    assert _history_turns() == 12


def test_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("SACP_CONTEXT_MAX_TURNS", "not-a-number")
    assert _history_turns() == 20


def test_never_below_floor(monkeypatch):
    monkeypatch.setenv("SACP_CONTEXT_MAX_TURNS", "1")
    assert _history_turns() == MVC_FLOOR_TURNS
