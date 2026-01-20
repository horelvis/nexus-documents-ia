"""
MCP Alfresco Server Entry Point.

Supports two transport modes:
1. STDIO (default): For subprocess communication
   - Run: python -m app.main

2. HTTP/SSE: For network communication
   - Run: python -m app.main --http
   - Or set: MCP_TRANSPORT=http

Usage:
    # STDIO mode (for MCP clients using subprocess)
    python -m app.main

    # HTTP mode (for network access)
    python -m app.main --http --port 8000

    # Or via environment
    MCP_TRANSPORT=http PORT=8000 python -m app.main
"""

import argparse
import asyncio
import logging
import os
import sys

from .server import create_server
from .core.config import settings, get_instances

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


async def run_stdio():
    """Run MCP server in STDIO mode."""
    from mcp.server.stdio import stdio_server

    logger.info("Starting MCP Alfresco Server in STDIO mode")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_http(host: str = "0.0.0.0", port: int = 8000):
    """
    Run MCP server in HTTP/SSE mode.

    Uses Starlette for HTTP server with SSE transport.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse
    from mcp.server.sse import SseServerTransport
    import uvicorn

    logger.info(f"Starting MCP Alfresco Server in HTTP mode on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        """Handle SSE connections."""
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    async def handle_messages(request):
        """Handle SSE message endpoint."""
        await sse.handle_post_message(
            request.scope, request.receive, request._send
        )

    async def health(request):
        """Health check endpoint."""
        instances = get_instances()
        return JSONResponse({
            "status": "healthy",
            "service": settings.service_name,
            "instances": list(instances.keys()),
        })

    async def info(request):
        """Server info endpoint."""
        instances = get_instances()
        return JSONResponse({
            "name": "mcp-alfresco-server",
            "version": "1.0.0",
            "protocol": "MCP",
            "transport": "HTTP/SSE",
            "instances": [
                {
                    "name": inst.name,
                    "url": inst.url,
                    "default_site": inst.default_site_id,
                }
                for inst in instances.values()
            ],
            "tools": [
                "alfresco_search",
                "alfresco_download",
                "alfresco_upload",
                "alfresco_list",
                "alfresco_get_metadata",
                "alfresco_get_versions",
                "alfresco_move",
                "alfresco_copy",
                "alfresco_delete",
                "alfresco_update_metadata",
                "alfresco_create_folder",
                "alfresco_get_sites",
            ],
        })

    app = Starlette(
        debug=settings.debug,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            Route("/sse", handle_sse, methods=["GET"]),
            Route("/messages/", handle_messages, methods=["POST"]),
        ],
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="debug" if settings.debug else "info",
    )
    server_uvicorn = uvicorn.Server(config)
    await server_uvicorn.serve()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Alfresco Server - Document management for Alfresco 7.x"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run in HTTP/SSE mode instead of STDIO",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="HTTP host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="HTTP port (default: 8000)",
    )

    args = parser.parse_args()

    # Check environment for transport mode
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    use_http = args.http or transport == "http"

    # Log configuration
    instances = get_instances()
    if instances:
        logger.info(f"Configured Alfresco instances: {list(instances.keys())}")
    else:
        logger.warning("No Alfresco instances configured!")

    # Run server
    if use_http:
        asyncio.run(run_http(args.host, args.port))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
