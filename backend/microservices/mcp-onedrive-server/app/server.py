"""
MCP Server for OneDrive.

Exposes OneDrive document management operations as MCP tools.
Configuration is loaded from the database using connector_id and tenant_id.
OAuth tokens are auto-refreshed when expired.
"""

import logging
from typing import Any, Dict

from mcp.server import Server
from mcp.types import Tool, TextContent

from .tools.onedrive_tools import (
    onedrive_list_connectors,
    onedrive_list_files,
    onedrive_search,
    onedrive_download,
    onedrive_get_metadata,
    onedrive_get_folder_tree,
    onedrive_create_folder,
    onedrive_upload,
    onedrive_move,
    onedrive_delete,
)

logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server with OneDrive tools."""

    server = Server("onedrive")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="onedrive_list_connectors",
                description=(
                    "List all active OneDrive connectors configured for the tenant. "
                    "Use this first to discover available OneDrive instances."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                    },
                    "required": ["tenant_id"],
                },
            ),
            Tool(
                name="onedrive_list_files",
                description=(
                    "List files in a OneDrive folder. "
                    "Returns files with metadata (name, type, size, modified date)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID (from onedrive_list_connectors)",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Folder item ID (default: connector's configured folder or root)",
                        },
                        "include_subfolders": {
                            "type": "boolean",
                            "description": "Recurse into subfolders",
                            "default": False,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum files to return",
                            "default": 50,
                        },
                    },
                    "required": ["connector_id", "tenant_id"],
                },
            ),
            Tool(
                name="onedrive_search",
                description=(
                    "Search files in OneDrive by query. "
                    "Searches file content and metadata."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Restrict search to a specific folder",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 50,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "query"],
                },
            ),
            Tool(
                name="onedrive_download",
                description=(
                    "Download file content from OneDrive. "
                    "Returns content as base64, along with filename and MIME type."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "OneDrive item ID",
                        },
                        "return_base64": {
                            "type": "boolean",
                            "description": "Return content as base64 string",
                            "default": True,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "file_id"],
                },
            ),
            Tool(
                name="onedrive_get_metadata",
                description=(
                    "Get detailed metadata for a file including path, "
                    "drive info, and sharing status."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "OneDrive item ID",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "file_id"],
                },
            ),
            Tool(
                name="onedrive_get_folder_tree",
                description="Get folder tree structure showing nested folders.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Root folder ID (default: connector's configured folder)",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum depth to traverse",
                            "default": 3,
                        },
                    },
                    "required": ["connector_id", "tenant_id"],
                },
            ),
            Tool(
                name="onedrive_create_folder",
                description="Create a new folder in OneDrive.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "name": {
                            "type": "string",
                            "description": "Folder name",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "Parent folder ID (optional)",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "name"],
                },
            ),
            Tool(
                name="onedrive_upload",
                description=(
                    "Upload a file to OneDrive. "
                    "Content must be provided as base64-encoded string."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "filename": {
                            "type": "string",
                            "description": "File name",
                        },
                        "content_base64": {
                            "type": "string",
                            "description": "File content as base64 string",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "MIME type",
                            "default": "application/octet-stream",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "Parent folder ID",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "filename", "content_base64"],
                },
            ),
            Tool(
                name="onedrive_move",
                description="Move an item to a different folder.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "Item ID to move",
                        },
                        "target_folder_id": {
                            "type": "string",
                            "description": "Destination folder ID",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "file_id", "target_folder_id"],
                },
            ),
            Tool(
                name="onedrive_delete",
                description=(
                    "Delete an item. Moves to recycle bin by default."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "OneDrive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "Item ID to delete",
                        },
                        "permanent": {
                            "type": "boolean",
                            "description": "Permanently delete (skip recycle bin)",
                            "default": False,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "file_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> list[TextContent]:
        """Execute a OneDrive tool and return results."""
        import json

        logger.info(f"Executing tool: {name}")

        tools = {
            "onedrive_list_connectors": onedrive_list_connectors,
            "onedrive_list_files": onedrive_list_files,
            "onedrive_search": onedrive_search,
            "onedrive_download": onedrive_download,
            "onedrive_get_metadata": onedrive_get_metadata,
            "onedrive_get_folder_tree": onedrive_get_folder_tree,
            "onedrive_create_folder": onedrive_create_folder,
            "onedrive_upload": onedrive_upload,
            "onedrive_move": onedrive_move,
            "onedrive_delete": onedrive_delete,
        }

        if name not in tools:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"success": False, "error": f"Unknown tool: {name}"}),
                )
            ]

        try:
            result = await tools[name](**arguments)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, default=str),
                )
            ]
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"success": False, "error": str(e)}),
                )
            ]

    return server
