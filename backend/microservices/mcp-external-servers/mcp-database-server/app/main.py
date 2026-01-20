"""
MCP Database Server Entry Point.

Provides read-only query tools for external databases via MCP protocol.
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
from app.tools import db_tools

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)

logger = logging.getLogger(__name__)

server = Server("mcp-database-server")

TOOLS = [
    Tool(
        name="query",
        description=db_tools.db_query.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "database_name": {"type": "string", "description": "Configured database name"},
                "query": {"type": "string", "description": "SQL SELECT query"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "params": {"type": "array", "description": "Query parameters"},
                "limit": {"type": "integer", "description": "Max rows", "default": 100},
            },
            "required": ["database_name", "query", "tenant_id"]
        }
    ),
    Tool(
        name="list_tables",
        description=db_tools.db_list_tables.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "database_name": {"type": "string", "description": "Database name"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "schema": {"type": "string", "description": "Schema name", "default": "public"},
            },
            "required": ["database_name", "tenant_id"]
        }
    ),
    Tool(
        name="describe_table",
        description=db_tools.db_describe_table.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "database_name": {"type": "string", "description": "Database name"},
                "table_name": {"type": "string", "description": "Table to describe"},
                "tenant_id": {"type": "string", "description": "Tenant identifier"},
                "schema": {"type": "string", "description": "Schema name", "default": "public"},
            },
            "required": ["database_name", "table_name", "tenant_id"]
        }
    ),
    Tool(
        name="list_databases",
        description=db_tools.list_databases.__doc__,
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
        if name == "query":
            result = await db_tools.db_query(**arguments)
        elif name == "list_tables":
            result = await db_tools.db_list_tables(**arguments)
        elif name == "describe_table":
            result = await db_tools.db_describe_table(**arguments)
        elif name == "list_databases":
            result = await db_tools.list_databases(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str, indent=2))]

    except Exception as e:
        logger.exception(f"Tool call failed: {name}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def handle_messages(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return Response(status_code=202)


async def health_check(request: Request):
    return JSONResponse({"status": "healthy", "service": "mcp-database-server"})


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
