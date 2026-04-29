"""Launch the MCP server (8750) and the Web UI (8751) in one process.

Both apps cooperate on the asyncio event loop via asyncio.gather. The
MCP app's lifespan provisions the pool + services; once MCP startup
completes we copy those services onto the Web UI app so both servers
share the same connection manager, repositories, and auth service.
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from src.mcp_server.app import create_app as create_mcp_app
from src.security import install_scrub_excepthook, install_scrub_filter
from src.web_ui.app import create_web_app
from src.web_ui.shared import prime_from_mcp_app

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
# Install credential-scrubbing on the root logger AND sys.excepthook before any
# real work runs. Without this, the spec §FR-012 log scrubber and the §Assumptions
# traceback scrubber are dead code (the functions exist but never get installed).
install_scrub_filter()
install_scrub_excepthook()
log = logging.getLogger("sacp.run_apps")


async def _run() -> None:
    """Start both uvicorn servers concurrently with shared services."""
    mcp_app = create_mcp_app()
    web_app = create_web_app()
    mcp = _server(mcp_app, port=8750)
    web = _server(web_app, port=8751)
    log.info("launching MCP (8750) and Web UI (8751)")
    mcp_task = asyncio.create_task(mcp.serve(), name="mcp-server")
    await _wait_for_mcp_ready(mcp_app)
    prime_from_mcp_app(web_app, mcp_app)
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


def main() -> None:
    """Blocking entrypoint."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
