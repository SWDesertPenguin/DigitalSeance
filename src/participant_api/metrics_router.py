# SPDX-License-Identifier: AGPL-3.0-or-later

"""GET /metrics endpoint -- Prometheus-format metrics surface (spec 016).

Mounted conditionally when ``SACP_METRICS_ENABLED=true``.  When disabled
(the default), this router is NOT included and the endpoint returns HTTP 404
from route absence -- identical pre-feature behavior (FR-007 / SC-005).

The endpoint is exempt from the network-layer rate limiter via
``EXEMPT_PATHS`` in ``src/middleware/network_rate_limit.py`` (FR-002).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["metrics"])

_BIND_PATH_DEFAULT = "/metrics"


def _metrics_enabled() -> bool:
    """Return True when SACP_METRICS_ENABLED=true/1 (case-insensitive)."""
    raw = os.environ.get("SACP_METRICS_ENABLED", "").strip().lower()
    return raw in ("true", "1")


def _bind_path() -> str:
    """Return the configured metrics path (default /metrics)."""
    raw = os.environ.get("SACP_METRICS_BIND_PATH", "").strip()
    return raw if raw else _BIND_PATH_DEFAULT


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    """Return Prometheus text-format metrics (FR-001 / FR-014).

    Returns HTTP 404 when metrics are disabled -- route is only registered
    when SACP_METRICS_ENABLED=true, so this handler only fires when enabled.
    The 404 branch here is a belt-and-suspenders guard for runtime disable.
    """
    del request  # no per-request data needed; metrics are pull-only
    if not _metrics_enabled():
        raise HTTPException(status_code=404, detail="Metrics not enabled")
    from src.observability.metrics_registry import get_registry

    data = generate_latest(get_registry())
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


def is_metrics_enabled() -> bool:
    """Public predicate for app.py conditional router inclusion."""
    return _metrics_enabled()


__all__ = ["is_metrics_enabled", "router"]
