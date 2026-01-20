"""
MCP REST API Server Entry Point.

Provides tools for calling external REST APIs via MCP protocol.
"""

import asyncio
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.requests import Request

from app.core.config import settings
from app.tools import api_tools

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)

logger = logging.getLogger(__name__)

# Create MCP server
server = Server("mcp-rest-api-server")

TOOLS = [
    Tool(
        name="get",
        description=api_tools.rest_get.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "endpoint_name": {"type": "string", "description": "Configured endpoint name"},
                "path": {"type": "string", "description": "API path"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "params": {"type": "object", "description": "Query parameters"},
                "headers": {"type": "object", "description": "Additional headers"},
            },
            "required": ["endpoint_name", "path", "tenant_id"]
        }
    ),
    Tool(
        name="post",
        description=api_tools.rest_post.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "endpoint_name": {"type": "string", "description": "Configured endpoint name"},
                "path": {"type": "string", "description": "API path"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "body": {"type": "object", "description": "Request body"},
                "params": {"type": "object", "description": "Query parameters"},
                "headers": {"type": "object", "description": "Additional headers"},
            },
            "required": ["endpoint_name", "path", "tenant_id"]
        }
    ),
    Tool(
        name="query",
        description=api_tools.rest_query.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "endpoint_name": {"type": "string", "description": "Configured endpoint name"},
                "path": {"type": "string", "description": "API path"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "params": {"type": "object", "description": "Query parameters"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 20},
            },
            "required": ["endpoint_name", "path", "tenant_id"]
        }
    ),
    Tool(
        name="list_endpoints",
        description=api_tools.list_endpoints.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
            },
            "required": ["tenant_id"]
        }
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    import json

    logger.info(f"Tool call: {name}")

    try:
        if name == "get":
            result = await api_tools.rest_get(**arguments)
        elif name == "post":
            result = await api_tools.rest_post(**arguments)
        elif name == "query":
            result = await api_tools.rest_query(**arguments)
        elif name == "list_endpoints":
            result = await api_tools.list_endpoints(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        logger.exception(f"Tool call failed: {name}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# HTTP/SSE transport
sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def handle_messages(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return Response(status_code=202)


async def health_check(request: Request):
    return JSONResponse({"status": "healthy", "service": "mcp-rest-api-server"})


app = Starlette(
    debug=settings.debug,
    routes=[
        Route("/health", health_check, methods=["GET"]),
        Route("/sse", handle_sse, methods=["GET"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
