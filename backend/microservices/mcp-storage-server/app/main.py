"""
MCP Storage Server Entry Point.

Supports two transport modes:
1. STDIO (default): For subprocess communication
2. HTTP/SSE: For network-based clients

Usage:
    # STDIO mode (default)
    python -m app.main

    # HTTP/SSE mode
    python -m app.main --http --port 8000

    # With uvicorn directly
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import argparse
import asyncio
import logging
import sys

from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,  # MCP uses stdout for protocol, logs go to stderr
)

logger = logging.getLogger(__name__)


def create_http_app():
    """
    Create a Starlette app for HTTP/SSE transport.

    This allows the MCP server to be accessed over HTTP with
    Server-Sent Events for bidirectional communication.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse, Response
    from starlette.requests import Request
    from mcp.server.sse import SseServerTransport

    from app.server import get_server

    server = get_server()
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        """Handle SSE connections from MCP clients."""
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options()
            )

    async def handle_messages(request: Request):
        """Handle message posts from MCP clients."""
        await sse_transport.handle_post_message(
            request.scope,
            request.receive,
            request._send,
        )
        return Response(status_code=202)

    async def health_check(request: Request):
        """Health check endpoint."""
        return JSONResponse({
            "status": "healthy",
            "service": "mcp-storage-server",
            "version": "1.0.0",
        })

    async def list_tools_http(request: Request):
        """List available tools (for debugging)."""
        from app.server import TOOLS
        return JSONResponse({
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description[:200] + "..." if len(tool.description or "") > 200 else tool.description,
                }
                for tool in TOOLS
            ]
        })

    routes = [
        Route("/health", health_check, methods=["GET"]),
        Route("/tools", list_tools_http, methods=["GET"]),
        Route("/sse", handle_sse, methods=["GET"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ]

    app = Starlette(
        debug=settings.debug,
        routes=routes,
    )

    return app


# Create HTTP app for uvicorn
app = create_http_app()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="MCP Storage Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run in HTTP/SSE mode instead of STDIO"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.service_port,
        help="Port for HTTP mode (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for HTTP mode (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    if args.http:
        # Run with uvicorn for HTTP mode
        import uvicorn
        logger.info(f"Starting MCP Storage Server (HTTP/SSE) on {args.host}:{args.port}")
        config = uvicorn.Config(
            app=app,
            host=args.host,
            port=args.port,
            log_level="debug" if settings.debug else "info",
        )
        server = uvicorn.Server(config)
        await server.serve()
    else:
        # Run in STDIO mode (default)
        from app.server import run_stdio
        logger.info("Starting MCP Storage Server (STDIO)")
        await run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
