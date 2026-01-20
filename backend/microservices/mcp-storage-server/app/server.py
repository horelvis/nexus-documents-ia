"""
MCP Storage Server Definition.

Defines the MCP server with all storage tools exposed via the
Model Context Protocol.

This server can be used with:
1. STDIO transport (subprocess): Good for local development
2. HTTP/SSE transport: Good for production with multiple clients
"""

import logging
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

from app.tools import storage_tools
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create MCP server instance
server = Server("mcp-storage-server")


# Tool definitions with JSON Schema for parameters
TOOLS = [
    Tool(
        name="upload",
        description=storage_tools.upload_file.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "content_base64": {
                    "type": "string",
                    "description": "File content encoded as base64 string"
                },
                "filename": {
                    "type": "string",
                    "description": "Name for the uploaded file"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier for storage isolation"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                },
                "content_type": {
                    "type": "string",
                    "description": "Optional MIME type"
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional key-value metadata"
                }
            },
            "required": ["content_base64", "filename", "tenant_id"]
        }
    ),
    Tool(
        name="download",
        description=storage_tools.download_file.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to download"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                },
                "return_base64": {
                    "type": "boolean",
                    "description": "Return content as base64 (default: true)",
                    "default": True
                }
            },
            "required": ["filename", "tenant_id"]
        }
    ),
    Tool(
        name="list",
        description=storage_tools.list_files.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "prefix": {
                    "type": "string",
                    "description": "Optional prefix to filter files",
                    "default": ""
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum files to return",
                    "default": 100
                }
            },
            "required": ["tenant_id"]
        }
    ),
    Tool(
        name="delete",
        description=storage_tools.delete_file.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to delete"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                }
            },
            "required": ["filename", "tenant_id"]
        }
    ),
    Tool(
        name="info",
        description=storage_tools.get_file_info.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                }
            },
            "required": ["filename", "tenant_id"]
        }
    ),
    Tool(
        name="signed_url",
        description=storage_tools.generate_signed_url.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET or PUT)",
                    "default": "GET",
                    "enum": ["GET", "PUT"]
                },
                "expiration_seconds": {
                    "type": "integer",
                    "description": "URL validity in seconds",
                    "default": 3600
                },
                "content_type": {
                    "type": "string",
                    "description": "Content type for PUT requests"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                }
            },
            "required": ["filename", "tenant_id"]
        }
    ),
    Tool(
        name="move",
        description=storage_tools.move_file.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Current filename/path"
                },
                "destination": {
                    "type": "string",
                    "description": "New filename/path"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                }
            },
            "required": ["source", "destination", "tenant_id"]
        }
    ),
    Tool(
        name="exists",
        description=storage_tools.file_exists.__doc__,
        inputSchema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to check"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier"
                },
                "user_id": {
                    "type": "string",
                    "description": "Optional user identifier"
                }
            },
            "required": ["filename", "tenant_id"]
        }
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available storage tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """
    Handle tool calls from MCP clients.

    Routes the call to the appropriate storage function and returns
    the result as JSON text content.
    """
    import json

    logger.info(f"Tool call: {name} with args: {list(arguments.keys())}")

    try:
        # Route to appropriate function
        if name == "upload":
            result = await storage_tools.upload_file(**arguments)
        elif name == "download":
            result = await storage_tools.download_file(**arguments)
        elif name == "list":
            result = await storage_tools.list_files(**arguments)
        elif name == "delete":
            result = await storage_tools.delete_file(**arguments)
        elif name == "info":
            result = await storage_tools.get_file_info(**arguments)
        elif name == "signed_url":
            result = await storage_tools.generate_signed_url(**arguments)
        elif name == "move":
            result = await storage_tools.move_file(**arguments)
        elif name == "exists":
            result = await storage_tools.file_exists(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]

    except Exception as e:
        logger.exception(f"Tool call failed: {name}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "tool": name
            })
        )]


async def run_stdio():
    """Run the server with STDIO transport (for subprocess communication)."""
    logger.info("Starting MCP Storage Server (STDIO transport)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def get_server() -> Server:
    """Get the MCP server instance."""
    return server
