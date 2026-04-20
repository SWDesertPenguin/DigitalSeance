"""Launch MCP server (8750) and Web UI (8751) in a single process.

Used as the Docker entrypoint. Each app runs its own uvicorn Server
instance and they cooperate on the asyncio event loop via gather().
When either exits, the process exits — restart policy lives in
docker-compose.
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
log = logging.getLogger("sacp.run_apps")


async def _run() -> None:
    """Start both uvicorn servers concurrently."""
    mcp = uvicorn.Server(
        uvicorn.Config(
            "src.mcp_server.app:create_app",
            host="0.0.0.0",  # noqa: S104 — intentional: containerized service
            port=8750,
            factory=True,
            log_level="info",
        )
    )
    web = uvicorn.Server(
        uvicorn.Config(
            "src.web_ui.app:create_web_app",
            host="0.0.0.0",  # noqa: S104 — intentional: containerized service
            port=8751,
            factory=True,
            log_level="info",
        )
    )
    log.info("launching MCP (8750) and Web UI (8751)")
    await asyncio.gather(mcp.serve(), web.serve())


def main() -> None:
    """Blocking entrypoint."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
