# SPDX-License-Identifier: AGPL-3.0-or-later

"""Launch the participant API server (8750) and the Web UI (8751) in one process.

Both apps cooperate on the asyncio event loop via asyncio.gather. The
participant API app's lifespan provisions the pool + services; once startup
completes we copy those services onto the Web UI app so both servers
share the same connection manager, repositories, and auth service.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import uvicorn

from src.config import (
    VALIDATORS,
    ConfigValidationError,
    validate_all,
)
from src.mcp_protocol.discovery import discovery_router
from src.participant_api.app import create_app as create_participant_api_app
from src.security import install_scrub_excepthook, install_scrub_filter
from src.web_ui.app import create_web_app
from src.web_ui.shared import prime_from_participant_api_app

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
# Install credential-scrubbing on the root logger AND sys.excepthook before any
# real work runs. Without this, the spec §FR-012 log scrubber and the §Assumptions
# traceback scrubber are dead code (the functions exist but never get installed).
install_scrub_filter()
install_scrub_excepthook()
log = logging.getLogger("sacp.run_apps")


async def _run() -> None:
    """Start both uvicorn servers concurrently with shared services."""
    mcp_app = create_participant_api_app()
    mcp_app.include_router(discovery_router)
    if os.environ.get("SACP_MCP_PROTOCOL_ENABLED", "false").lower() == "true":
        from src.mcp_protocol.transport import mcp_router

        mcp_app.include_router(mcp_router)
    web_app = create_web_app()
    mcp = _server(mcp_app, port=8750)
    web = _server(web_app, port=8751)
    log.info("launching participant API (8750) and Web UI (8751)")
    mcp_task = asyncio.create_task(mcp.serve(), name="participant-api-server")
    await _wait_for_mcp_ready(mcp_app)
    prime_from_participant_api_app(web_app, mcp_app)
    web_task = asyncio.create_task(web.serve(), name="web-ui-server")
    await asyncio.gather(mcp_task, web_task)


def _server(app, port: int) -> uvicorn.Server:  # type: ignore[no-untyped-def]
    """Build a uvicorn Server bound to 0.0.0.0 for a given port.

    ws_max_size caps WebSocket payloads at 256 KB (011 §FR-013 / CHK013).
    The default uvicorn cap is 16 MB which is large enough that a malicious
    server (or compromised orchestrator) could OOM a browser tab via a
    single oversized frame. SACP messages are bounded above by the
    `MAX_MESSAGE_CONTENT_CHARS = 2_000` cap on inject_message, so 256 KB
    leaves comfortable headroom for state_snapshot payloads while closing
    the OOM surface.
    """
    return uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",  # noqa: S104 — containerized service
            port=port,
            log_level="info",
            ws_max_size=256 * 1024,
        )
    )


async def _wait_for_mcp_ready(mcp_app) -> None:  # type: ignore[no-untyped-def]
    """Poll until the MCP app's lifespan has attached app.state.pool."""
    for _ in range(300):  # up to 30s at 100ms per tick
        if hasattr(mcp_app.state, "pool"):
            return
        await asyncio.sleep(0.1)
    log.warning("MCP app did not publish pool within 30s; web UI may start without services")


def _print_validation(success: bool) -> None:
    """Emit the documented success line per contracts/config-validator-cli.md."""
    if success:
        print(f"config validation: OK ({len(VALIDATORS)} vars validated)")
    else:
        print("config validation: FAIL")


def _run_validation() -> int:
    """Run V16 startup validation; return 0 on clean, 1 on any failure."""
    try:
        validate_all()
    except ConfigValidationError as exc:
        _print_validation(success=False)
        for failure in exc.failures:
            print(f"  {failure.var_name}: {failure.reason}", file=sys.stderr)
        return 1
    _print_validation(success=True)
    return 0


def main() -> None:
    """Blocking entrypoint. Validates config before binding any port."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-config-only",
        action="store_true",
        help="Validate every SACP_* env var and exit; do not start the server.",
    )
    args = parser.parse_args()
    rc = _run_validation()
    if args.validate_config_only or rc != 0:
        sys.exit(rc)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
