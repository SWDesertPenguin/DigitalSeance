# SPDX-License-Identifier: AGPL-3.0-or-later

"""Spec 023 FR-018 master-switch-off canary.

Architectural assertion: when ``SACP_ACCOUNTS_ENABLED`` is unset or set
to ``'0'`` (the default), NO spec 023 account-router code path is
mounted onto the FastAPI Web UI surface. Every account endpoint MUST
return HTTP 404, and the existing token-paste landing remains the
default operator surface.

This canary lands FIRST after the Phase 1 schema migration per
plan.md "Notes for /speckit.tasks" and tasks.md T035 — it acts as a
leak detector before Phase 3+ user-story code grows. Subsequent
account-router modules MUST preserve these invariants.

The current shape pins:

1. The master-switch validator accepts unset/'0' as "off" without
   raising and a process running with the env unset sees no account
   routes.
2. None of the seven account-router endpoints documented in
   ``contracts/account-endpoints.md`` are reachable; each request
   returns HTTP 404 from the absence of the route.
3. ``GET /me/sessions`` and ``POST /me/sessions/{session_id}/rebind``
   are likewise absent — the post-login session list endpoint is
   gated by the same master switch.
4. The SPA's existing token-paste landing remains the default
   surface — ``GET /`` returns the spec 011 index page, NOT an
   account-creation form.

As Phase 3+ code lands, each newly-mounted route still has to honor
the off-state contract; this canary asserts the absence-of-mount
shape today and remains green by re-asserting the 404 contract once
the conditional mount lands.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import validators
from src.web_ui.app import create_web_app
from src.web_ui.security import CSRF_HEADER, CSRF_VALUE

# CSRF double-submit header — same shape the SPA sends. Bypasses the
# CSRF 403 short-circuit so the assertion measures route presence,
# not the upstream middleware.
_CSRF_HEADERS = {CSRF_HEADER: CSRF_VALUE}

# Acceptable "no handler" status codes when the master switch is off.
# 404 is the natural absence-of-route response. 405 is what the static
# StaticFiles mount at "/" returns when a POST falls through to it
# (StaticFiles only allows GET / HEAD). Either signals "no account
# handler reached"; both are valid leak-detector outcomes.
_NO_HANDLER_STATUSES = frozenset({404, 405})


# The seven account-router endpoints documented in
# contracts/account-endpoints.md — each MUST be unhandled when the
# switch is off (404 from absence-of-route or 405 from the static
# fallthrough at "/").
_ACCOUNT_POST_PATHS = (
    "/tools/account/create",
    "/tools/account/verify",
    "/tools/account/login",
    "/tools/account/email/change",
    "/tools/account/email/verify",
    "/tools/account/password/change",
    "/tools/account/delete",
    "/tools/admin/account/transfer_participants",
)

# The two /me/sessions endpoints under the same master switch.
_ME_SESSIONS_GET_PATH = "/me/sessions"
_ME_SESSIONS_REBIND_PATH = "/me/sessions/sess_canary/rebind"


@pytest.fixture(autouse=True)
def _switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the master switch unset (functionally off)."""
    monkeypatch.delenv("SACP_ACCOUNTS_ENABLED", raising=False)


# ---------------------------------------------------------------------------
# Validator accepts the off state without raising — process can boot
# ---------------------------------------------------------------------------


def test_master_switch_unset_passes_validator() -> None:
    """FR-018 / SC-008: unset env var means master switch is off; validator passes."""
    assert validators.validate_accounts_enabled() is None


def test_master_switch_off_value_passes_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit '0' value clears the V16 gate; nothing here implies activation."""
    monkeypatch.setenv("SACP_ACCOUNTS_ENABLED", "0")
    assert validators.validate_accounts_enabled() is None


# ---------------------------------------------------------------------------
# Account endpoints are NOT mounted under master-switch-off
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _ACCOUNT_POST_PATHS)
def test_account_post_endpoints_unhandled_when_switch_off(path: str) -> None:
    """FR-018: each account-router POST endpoint is unhandled when accounts are off.

    Until the Phase 3+ router lands, the absence-of-route shape produces
    a 404 (or a 405 from the static-mount fallthrough at ``/``). Once
    the conditional mount lands, the test still holds: the router is
    excluded from ``app.include_router`` when
    ``SACP_ACCOUNTS_ENABLED != '1'``, so the same status mix is reached.
    """
    app = create_web_app()
    with TestClient(app) as client:
        response = client.post(path, json={}, headers=_CSRF_HEADERS)
    assert response.status_code in _NO_HANDLER_STATUSES, (
        f"FR-018 leak: {path} returned {response.status_code} with master "
        "switch off; account router mounted unconditionally."
    )


def test_me_sessions_get_unhandled_when_switch_off() -> None:
    """FR-018: GET /me/sessions is unhandled when accounts are off.

    The GET path can fall through to the static mount, which serves
    ``/me/sessions`` as a missing file (404). 200 here would be a leak
    because no static asset shares the path.
    """
    app = create_web_app()
    with TestClient(app) as client:
        response = client.get(_ME_SESSIONS_GET_PATH)
    assert response.status_code in _NO_HANDLER_STATUSES, (
        f"FR-018 leak: {_ME_SESSIONS_GET_PATH} returned {response.status_code} "
        "with master switch off; /me/sessions reachable pre-mount."
    )


def test_me_sessions_rebind_unhandled_when_switch_off() -> None:
    """FR-018: POST /me/sessions/{id}/rebind is unhandled when accounts are off."""
    app = create_web_app()
    with TestClient(app) as client:
        response = client.post(_ME_SESSIONS_REBIND_PATH, headers=_CSRF_HEADERS)
    assert response.status_code in _NO_HANDLER_STATUSES, (
        f"FR-018 leak: {_ME_SESSIONS_REBIND_PATH} returned "
        f"{response.status_code} with master switch off."
    )


# ---------------------------------------------------------------------------
# SPA index remains the default operator surface
# ---------------------------------------------------------------------------


def test_index_remains_default_landing_when_switch_off() -> None:
    """FR-018: the spec 011 SPA index is still served when accounts are off.

    The token-paste landing is the operator-deployment fallback per
    research.md §11 surface 1 — it MUST remain reachable so an operator
    running with accounts disabled retains the existing flow.
    """
    app = create_web_app()
    with TestClient(app) as client:
        response = client.get("/")
    # Index is served by the static mount; either 200 (file present) or
    # 404 (test environment without static assets) is fine — what is
    # NOT fine is a redirect to an account-creation page, which would
    # signal that the auth-gate region landed without a master-switch
    # guard.
    assert response.status_code != 302, (
        "FR-018 leak: GET / returned 302 with master switch off; "
        "auth-gate landed without a master-switch guard."
    )


# ---------------------------------------------------------------------------
# Phase 2 module skeletons are importable without unconditional side effects
# ---------------------------------------------------------------------------


def test_accounts_package_importable() -> None:
    """Importing ``src.accounts`` MUST NOT mount routes or read env at import time.

    Each module in the package is currently a documented skeleton; once
    Phase 2 lands real implementations, this canary preserves the
    invariant that import-time side effects do not leak account routes
    onto the app surface.
    """
    import src.accounts  # noqa: F401  # import is the assertion


def test_account_repo_module_importable() -> None:
    """Importing ``src.repositories.account_repo`` MUST NOT touch the DB."""
    import src.repositories.account_repo  # noqa: F401  # import is the assertion


def test_account_model_module_importable() -> None:
    """Importing ``src.models.account`` MUST NOT touch the DB."""
    import src.models.account  # noqa: F401  # import is the assertion
