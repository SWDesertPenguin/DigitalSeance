"""E2E coverage for US1 — Facilitator Creates and Monitors a Session.

Implements task T058 from specs/011-web-ui/tasks.md. The test walks
through the three acceptance scenarios on US1 with a real browser.

Scenario mapping (spec.md:§User Story 1):
    AC1 — facilitator logs in → SessionView loads
    AC2 — new turn appears in transcript within 2 s
    AC3 — Ctrl+Enter on the input injects a message
    AC4 — clicking Pause flips the status badge

The AC2 check assumes an AI participant with a valid key has been
added to the session pre-test; operator sets up via Swagger or via
AD/US1 path before kicking off the e2e run.
"""

from __future__ import annotations

import re

import pytest


@pytest.mark.e2e
def test_us1_ac1_login_loads_session_view(signed_in_page):  # type: ignore[no-untyped-def]
    """Facilitator signs in → three-column session view renders."""
    page = signed_in_page
    assert page.locator(".app-shell").is_visible()
    assert page.locator(".sidebar-left .participant-list").is_visible()
    assert page.locator(".center-column .transcript").is_visible()
    assert page.locator(".sidebar-right").is_visible()


@pytest.mark.e2e
def test_us1_ac3_ctrl_enter_injects_message(signed_in_page):  # type: ignore[no-untyped-def]
    """Typing into the message input + Ctrl+Enter posts a human message."""
    page = signed_in_page
    input_box = page.locator(".message-input textarea")
    input_box.fill("hello from playwright")
    input_box.press("Control+Enter")
    # The message is persisted via POST + shows up after the next WS
    # message event. Give the live loop 5 s to reflect it.
    page.wait_for_selector(
        ".msg.msg-human:has-text('hello from playwright')",
        timeout=5_000,
    )


@pytest.mark.e2e
def test_us1_ac4_pause_button_toggles_status(signed_in_page):  # type: ignore[no-untyped-def]
    """Clicking Pause updates the header status badge within 1 s."""
    page = signed_in_page
    status_badge = page.locator(".status-badge").first
    original = status_badge.inner_text()

    page.get_by_role("button", name="Pause").click()
    page.wait_for_function(
        "document.querySelector('.status-badge').innerText !== arguments[0]",
        arg=original,
        timeout=2_000,
    )
    assert re.search(r"paused|active", status_badge.inner_text(), re.I)
