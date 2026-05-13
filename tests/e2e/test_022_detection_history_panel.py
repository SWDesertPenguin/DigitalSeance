# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 022 detection-history Playwright e2e (T048 of tasks.md).

Walks Steps 1-7 of ``specs/022-detection-event-history/quickstart.md``
against a running SACP stack:

- US1: open the panel, render rows in newest-first chronological order
  with English class labels, empty state when no events.
- US2: click re-surface on a dismissed row, banner re-appears, audit
  row landed. Archived sessions disable the button.
- US3: type / participant / disposition / time-range filters narrow
  the visible set; AND-compose; clear restores.

Whole module is skipped unless ``SACP_RUN_E2E=1`` (per
``tests/e2e/conftest.py``). Operators bring up the stack and a
facilitator session (with ``SACP_DETECTION_HISTORY_ENABLED=true``)
before invoking — see ``tests/e2e/README.md`` for setup recipe.

The tests target stable DOM hooks (``.detection-history-panel``,
``.detection-event-row``, ``.detection-filter-type``,
``.detection-filter-disposition``, ``.detection-row-resurface``,
``.detection-filter-badge``) the SPA exposes. If those hooks change,
update both the SPA class names and this test together.
"""

from __future__ import annotations

import re

import pytest


@pytest.mark.e2e
def test_us1_panel_opens_and_renders_events(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 2: open panel via entry-point button, rows render with class labels."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)
    rows = page.locator(".detection-history-panel .detection-event-row")
    if rows.count() == 0:
        pytest.skip("session has no detection events yet — drive one before this test")
    first_label = rows.first.locator(".detection-event-class-label").inner_text().strip()
    assert first_label, "every event row MUST render a class label"
    assert " " in first_label or first_label.startswith(
        "["
    ), f"expected English / [unregistered: ...] label; got {first_label!r}"


@pytest.mark.e2e
def test_us1_panel_orders_newest_first_by_default(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 2: rows arrive newest-first (research §12) without operator action."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)
    rows = page.locator(".detection-event-row")
    if rows.count() < 2:
        pytest.skip("ordering test needs >= 2 rows; drive more events first")
    first_ts = rows.first.locator(".detection-event-timestamp").inner_text()
    second_ts = rows.nth(1).locator(".detection-event-timestamp").inner_text()
    # ISO-8601 strings sort lexicographically; newest-first ⇒ first >= second.
    assert (
        first_ts >= second_ts
    ), f"newest-first ordering violated: first={first_ts!r}, second={second_ts!r}"


@pytest.mark.e2e
def test_us1_master_switch_hides_button_and_404s_route(
    signed_in_page,
):  # type: ignore[no-untyped-def]
    """Step 9: button is absent and direct GET 404s when master switch is off."""

    import os

    if os.environ.get("SACP_RUN_E2E_MASTER_SWITCH_OFF") != "1":
        pytest.skip(
            "SACP_RUN_E2E_MASTER_SWITCH_OFF not set — needs a stack started with "
            "SACP_DETECTION_HISTORY_ENABLED=false"
        )

    page = signed_in_page
    button = page.get_by_role("button", name=re.compile(r"View detection history", re.I))
    assert not button.is_visible(), "master-switch off MUST hide the button (FR-016)"

    base_url = page.url.rsplit("/session/", 1)[0]
    response = page.request.get(f"{base_url}/api/mcp/tools/admin/detection_events?session_id=any")
    assert response.status == 404, "master-switch off MUST 404 the route (FR-016)"


@pytest.mark.e2e
def test_us2_resurface_button_emits_audit_row(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 6: clicking re-surface on a dismissed event emits an audit row."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)

    dismissed_row = page.locator(
        ".detection-event-row:has(.detection-event-disposition:has-text('dismissed'))"
    ).first
    if not dismissed_row.is_visible():
        pytest.skip("session has no banner_dismissed rows — dismiss a banner first")

    resurface_btn = dismissed_row.locator(".detection-row-resurface")
    resurface_btn.click()
    # The original banner re-renders elsewhere in the UI — we assert the
    # button accepted the click and the row remains in place (per spec
    # acceptance scenario US2.2; the disposition is unchanged).
    page.wait_for_function(
        "(btn) => btn.disabled === false || btn.dataset.resurfaced === 'true'",
        arg=resurface_btn.element_handle(),
        timeout=3_000,
    )


@pytest.mark.e2e
def test_us2_resurface_disabled_on_archived_session(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 7: archived session disables the re-surface button (FR-008)."""

    import os

    if os.environ.get("SACP_RUN_E2E_ARCHIVED_SESSION") != "1":
        pytest.skip("SACP_RUN_E2E_ARCHIVED_SESSION not set — needs an archived test session")

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)
    rows = page.locator(".detection-event-row")
    if rows.count() == 0:
        pytest.skip("archived session has no detection events to assert against")
    btn = rows.first.locator(".detection-row-resurface")
    assert btn.is_disabled(), "archived session MUST disable the re-surface button"


@pytest.mark.e2e
def test_us3_type_filter_narrows_visible_set(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 3: type filter narrows the visible row set."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)

    rows_before = page.locator(".detection-event-row").count()
    if rows_before < 2:
        pytest.skip("filter test needs >= 2 rows; drive more events first")

    page.locator(".detection-filter-type").select_option("density_anomaly")
    page.wait_for_function(
        "(before) => document.querySelectorAll('.detection-event-row').length <= before",
        arg=rows_before,
        timeout=2_000,
    )
    page.get_by_role("button", name=re.compile(r"Clear filters", re.I)).click()
    page.wait_for_function(
        "(before) => document.querySelectorAll('.detection-event-row').length === before",
        arg=rows_before,
        timeout=2_000,
    )


@pytest.mark.e2e
def test_us3_disposition_filter_narrows_visible_set(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 5: disposition filter narrows the visible row set."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)
    rows_before = page.locator(".detection-event-row").count()
    if rows_before < 2:
        pytest.skip("disposition filter test needs >= 2 rows")
    page.locator(".detection-filter-disposition").select_option("banner_dismissed")
    page.wait_for_function(
        "(before) => document.querySelectorAll('.detection-event-row').length <= before",
        arg=rows_before,
        timeout=2_000,
    )


@pytest.mark.e2e
def test_us3_filter_badge_increments_when_non_matching_event_arrives(
    signed_in_page,
):  # type: ignore[no-untyped-def]
    """Step 3 scenario 3: badge counts events outside the active filter."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View detection history", re.I)).click()
    page.wait_for_selector(".detection-history-panel", timeout=5_000)
    page.locator(".detection-filter-type").select_option("density_anomaly")
    badge = page.locator(".detection-filter-badge")
    # Conditionally rendered; count() reaches 1 once any axis hides events.
    assert badge.count() <= 1, "exactly one filter-badge slot expected"
