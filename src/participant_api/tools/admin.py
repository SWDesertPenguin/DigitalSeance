# SPDX-License-Identifier: AGPL-3.0-or-later

"""Admin tool endpoints — read-only audit-log surface for facilitators (spec 029).

The router mounts conditionally on ``SACP_AUDIT_VIEWER_ENABLED=true``; when
disabled the route is absent and ALL callers receive ``HTTP 404`` per FR-018.
The mount decision lives in ``src/participant_api/app.py`` so the master switch
hides the surface from probe-based discovery.

Authorization (per ``contracts/audit-log-endpoint.md``):

- Caller MUST be a facilitator (FR-002) — non-facilitators receive ``HTTP 403``.
- Caller MUST belong to the requested session (FR-003) — cross-session reads
  receive ``HTTP 403``.

Pagination (per FR-005): offset-based with ``offset`` (default 0) and ``limit``
(default ``SACP_AUDIT_VIEWER_PAGE_SIZE`` = 50, hard ceiling 500). Out-of-range
parameters return ``HTTP 400``.

Side effects: NONE (FR-004). The endpoint is read-only; no audit-of-the-audit
row is written, the act of viewing is not itself an audit event.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request

from src.models.participant import Participant
from src.orchestrator.audit_log_view import page_to_payload
from src.participant_api.middleware import get_current_participant

router = APIRouter(prefix="/tools/admin", tags=["admin"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


@router.get("/audit_log")
async def get_audit_log(
    request: Request,
    session_id: str,
    offset: int = 0,
    limit: int | None = None,
    participant: Participant = Depends(get_current_participant),
) -> dict:
    """Return a paginated, decorated audit-log page for the session.

    See ``specs/029-audit-log-viewer/contracts/audit-log-endpoint.md`` for
    the full request/response contract. Server-side scrubbing per FR-014
    is applied inside ``log_repo.get_audit_log_page`` before the rows
    leave the repository.
    """
    _authorize(participant, session_id)
    resolved_limit = _resolve_limit(limit)
    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_params", "message": "offset must be >= 0"},
        )
    retention_days = _resolved_retention_days()
    state = request.app.state
    page = await state.log_repo.get_audit_log_page(
        session_id,
        offset=offset,
        limit=resolved_limit,
        retention_days=retention_days,
    )
    return page_to_payload(page)


def _authorize(participant: Participant, session_id: str) -> None:
    """Enforce facilitator-only + session-binding authorization."""
    if participant.role != "facilitator":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "facilitator_only",
                "message": "audit log access requires facilitator role",
            },
        )
    if participant.session_id != session_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "facilitator_only",
                "message": "audit log access requires facilitator role",
            },
        )


def _resolve_limit(limit: int | None) -> int:
    """Resolve and bound the ``limit`` query parameter.

    Falls back to the env-var default when unset; rejects values outside
    ``[1, env_max]``. The validator at startup already constrained the env
    var to ``[10, 500]``; this function tightens to the per-call ceiling.
    """
    env_max = _env_max_page_size()
    if limit is None:
        return min(DEFAULT_PAGE_SIZE, env_max)
    if limit < 1 or limit > MAX_PAGE_SIZE or limit > env_max:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_params",
                "message": f"limit must be between 1 and {min(MAX_PAGE_SIZE, env_max)}",
            },
        )
    return limit


def _env_max_page_size() -> int:
    """Read the env-var page-size cap (validator already constrained the value)."""
    raw = os.environ.get("SACP_AUDIT_VIEWER_PAGE_SIZE")
    if raw is None or raw.strip() == "":
        return DEFAULT_PAGE_SIZE
    try:
        return int(raw)
    except ValueError:
        # Validator would have refused to bind; defensive fallback.
        return DEFAULT_PAGE_SIZE


def _resolved_retention_days() -> int | None:
    """Read the env-var retention cap; ``None`` means no WHERE clause."""
    raw = os.environ.get("SACP_AUDIT_VIEWER_RETENTION_DAYS")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def is_audit_viewer_enabled() -> bool:
    """Return True when the master switch ``SACP_AUDIT_VIEWER_ENABLED`` is on.

    Treats any truthy bool-string as enabled (``true``/``1`` case-insensitive).
    Validator already constrained valid values; this helper is a thin parser.
    """
    raw = os.environ.get("SACP_AUDIT_VIEWER_ENABLED", "")
    return raw.strip().lower() in ("true", "1")
