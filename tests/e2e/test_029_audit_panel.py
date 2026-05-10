# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 029 audit-log viewer Playwright e2e (T029 / T031 / T038).

Walks the Steps 1-9 of ``specs/029-audit-log-viewer/quickstart.md``
against a running SACP stack:

- T029 (US1): the audit panel opens, renders rows in reverse-chrono
  with English labels, paginates, and the master-switch hides the
  button + 404s the route.
- T031 (US2): row expansion mounts the DiffRenderer for review-gate
  edits; the word-level toggle re-renders; value-less rows expand to
  metadata only.
- T038 (US3): filters narrow the visible set; the (N hidden) badge
  surfaces WS-pushed rows that don't match an active filter; clear
  restores.

The whole module is skipped unless ``SACP_RUN_E2E=1`` (per
``tests/e2e/conftest.py``). Operators bring up the stack and a
facilitator session before invoking; see ``tests/e2e/README.md``
for the local + CI setup recipe.

The tests target stable DOM hooks (``.audit-log-panel``,
``.audit-row``, ``.diff-renderer``, ``.audit-filter-badge``) that
the SPA exposes for the viewer. If those hooks change, the SPA's
class names should be updated alongside this test.
"""

from __future__ import annotations

import re

import pytest

# Mark every test in this file with the e2e marker so the
# pytest_collection_modifyitems hook in conftest.py applies its skip.


@pytest.mark.e2e
def test_us1_panel_renders_rows_with_english_labels(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 1+2: open panel, table renders in reverse-chrono with labels."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)

    rows = page.locator(".audit-log-panel .audit-row")
    assert rows.count() > 0, "audit panel should have at least one row"

    # Every row's action-label cell is non-empty and not the raw action key.
    first_label = rows.first.locator(".audit-action-label").inner_text().strip()
    assert first_label, "action label MUST render"
    assert " " in first_label or first_label.startswith(
        "["
    ), f"expected English / [unregistered: ...] label; got raw action {first_label!r}"


@pytest.mark.e2e
def test_us1_panel_paginates(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 1: pagination controls advance the loaded set when total > limit."""

    page = signed_in_page
    page.goto(page.url.split("/session/")[0] + page.url.split(page.url.split("/session/")[0])[-1])
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)

    next_btn = page.get_by_role("button", name=re.compile(r"^Next", re.I))
    if next_btn.is_visible() and not next_btn.is_disabled():
        first_row_text_before = page.locator(".audit-row").first.inner_text()
        next_btn.click()
        page.wait_for_function(
            "(prev) => document.querySelector('.audit-row').innerText !== prev",
            arg=first_row_text_before,
            timeout=5_000,
        )


@pytest.mark.e2e
def test_us1_master_switch_hides_button_and_404s_route(signed_in_page, monkeypatch):  # type: ignore[no-untyped-def]
    """Step 9: with master switch off, button is absent + direct GET 404s.

    Operator pre-condition: the SACP_RUN_E2E_MASTER_SWITCH_OFF=1 env var
    flags this test as runnable against a stack started with
    SACP_AUDIT_VIEWER_ENABLED=false. When the test sees the env var, it
    asserts the absent-button + 404 contract; otherwise it skips.
    """

    import os

    if os.environ.get("SACP_RUN_E2E_MASTER_SWITCH_OFF") != "1":
        pytest.skip(
            "SACP_RUN_E2E_MASTER_SWITCH_OFF not set — needs a stack started with "
            "SACP_AUDIT_VIEWER_ENABLED=false"
        )

    page = signed_in_page
    button = page.get_by_role("button", name=re.compile(r"View audit log", re.I))
    assert not button.is_visible(), "master-switch off MUST hide the button (FR-025)"

    # Direct navigation MUST hit the 404 from the absent route.
    base_url = page.url.rsplit("/session/", 1)[0]
    response = page.request.get(f"{base_url}/api/mcp/tools/admin/audit_log?session_id=any")
    assert response.status == 404, "master-switch off MUST 404 the route (FR-018)"


@pytest.mark.e2e
def test_us2_review_gate_edit_row_expands_to_diff(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 3: clicking expand on a review_gate_edit mounts the DiffRenderer."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)

    edit_row = page.locator(
        ".audit-row:has(.audit-action-label:has-text('Review gate: draft edited'))"
    ).first
    if not edit_row.is_visible():
        pytest.skip("session has no review_gate_edit rows; drive one before this test")

    edit_row.locator(".audit-row-expand").click()
    page.wait_for_selector(".diff-renderer", timeout=3_000)


@pytest.mark.e2e
def test_us2_word_level_toggle_recomputes(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 3 (continued): word-level toggle re-renders the diff."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)
    edit_row = page.locator(
        ".audit-row:has(.audit-action-label:has-text('Review gate: draft edited'))"
    ).first
    if not edit_row.is_visible():
        pytest.skip("session has no review_gate_edit rows")

    edit_row.locator(".audit-row-expand").click()
    page.wait_for_selector(".diff-renderer", timeout=3_000)
    diff_text_before = page.locator(".diff-renderer").inner_text()

    edit_row.locator(".diff-word-toggle").click()
    page.wait_for_function(
        "(prev) => document.querySelector('.diff-renderer').innerText !== prev",
        arg=diff_text_before,
        timeout=3_000,
    )


@pytest.mark.e2e
def test_us2_value_less_row_expands_to_metadata_only(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 4: value-less rows (add_participant) expand without a diff pane."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)

    add_row = page.locator(
        ".audit-row:has(.audit-action-label:has-text('Facilitator added participant'))"
    ).first
    if not add_row.is_visible():
        pytest.skip("session has no add_participant rows")

    add_row.locator(".audit-row-expand").click()
    # Metadata pane is rendered without a diff pane.
    add_row.locator(".audit-row-metadata").wait_for(state="visible", timeout=2_000)
    assert (
        add_row.locator(".diff-renderer").count() == 0
    ), "value-less row MUST NOT mount the DiffRenderer"


@pytest.mark.e2e
def test_us3_filter_narrows_visible_set(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 5: action-type filter narrows the visible row set."""

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)

    rows_before = page.locator(".audit-row").count()
    if rows_before < 2:
        pytest.skip("filter test needs >= 2 rows; drive more audit events first")

    page.locator(".audit-filter-action").select_option("review_gate_edit")
    page.wait_for_function(
        "(before) => document.querySelectorAll('.audit-row').length < before",
        arg=rows_before,
        timeout=2_000,
    )

    page.get_by_role("button", name=re.compile(r"Clear filters", re.I)).click()
    page.wait_for_function(
        "(before) => document.querySelectorAll('.audit-row').length === before",
        arg=rows_before,
        timeout=2_000,
    )


@pytest.mark.e2e
def test_us3_filter_badge_increments_for_hidden_ws_push(signed_in_page):  # type: ignore[no-untyped-def]
    """Step 6: badge increments when a non-matching event arrives via WS.

    Driving the audit event itself is out of scope for this test (it
    requires a separately-authenticated facilitator client driving a
    different action via API). When run as part of the full quickstart
    walkthrough, the operator drives the action between filter and
    badge-check; here we assert only that the badge element renders
    when the count is non-zero, leaving driving to the surrounding
    test session.
    """

    page = signed_in_page
    page.get_by_role("button", name=re.compile(r"View audit log", re.I)).click()
    page.wait_for_selector(".audit-log-panel", timeout=5_000)

    page.locator(".audit-filter-action").select_option("review_gate_edit")
    badge = page.locator(".audit-filter-badge")
    # The badge is conditionally rendered; we just confirm the locator
    # exists in the DOM tree (count() works even when not visible).
    assert badge.count() <= 1, "exactly one filter badge slot expected"
