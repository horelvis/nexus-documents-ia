"""
MCP Server for Google Drive.

Exposes Google Drive document management operations as MCP tools.
Configuration is loaded from the database using connector_id and tenant_id.
OAuth tokens are auto-refreshed when expired.
"""

import logging
from typing import Any, Dict

from mcp.server import Server
from mcp.types import Tool, TextContent

from .tools.drive_tools import (
    gdrive_list_connectors,
    gdrive_list_files,
    gdrive_search,
    gdrive_download,
    gdrive_get_metadata,
    gdrive_get_folder_tree,
    gdrive_create_folder,
    gdrive_upload,
    gdrive_move,
    gdrive_delete,
)

logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server with Google Drive tools."""

    server = Server("google-drive")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="gdrive_list_connectors",
                description=(
                    "List all active Google Drive connectors configured for the tenant. "
                    "Use this first to discover available Google Drive instances."
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
                name="gdrive_list_files",
                description=(
                    "List files in a Google Drive folder. "
                    "Returns files with metadata (name, type, size, modified date)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID (from gdrive_list_connectors)",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Folder ID (default: connector's configured folder or root)",
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
                name="gdrive_search",
                description=(
                    "Search files in Google Drive by full-text query. "
                    "Searches file content and metadata."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
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
                name="gdrive_download",
                description=(
                    "Download file content from Google Drive. "
                    "Returns content as base64, along with filename and MIME type. "
                    "Google Docs/Sheets/Slides are exported to Office formats."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "Google Drive file ID",
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
                name="gdrive_get_metadata",
                description=(
                    "Get detailed metadata for a file including owners, "
                    "permissions, and sharing info."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "Google Drive file ID",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "file_id"],
                },
            ),
            Tool(
                name="gdrive_get_folder_tree",
                description="Get folder tree structure showing nested folders.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
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
                name="gdrive_create_folder",
                description="Create a new folder in Google Drive.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
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
                name="gdrive_upload",
                description=(
                    "Upload a file to Google Drive. "
                    "Content must be provided as base64-encoded string."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
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
                name="gdrive_move",
                description="Move a file to a different folder.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "File ID to move",
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
                name="gdrive_delete",
                description=(
                    "Delete a file. By default, moves to trash. "
                    "Use permanent=true to permanently delete."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Google Drive connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "file_id": {
                            "type": "string",
                            "description": "File ID to delete",
                        },
                        "permanent": {
                            "type": "boolean",
                            "description": "Permanently delete (skip trash)",
                            "default": False,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "file_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> list[TextContent]:
        """Execute a Google Drive tool and return results."""
        import json

        logger.info(f"Executing tool: {name}")

        tools = {
            "gdrive_list_connectors": gdrive_list_connectors,
            "gdrive_list_files": gdrive_list_files,
            "gdrive_search": gdrive_search,
            "gdrive_download": gdrive_download,
            "gdrive_get_metadata": gdrive_get_metadata,
            "gdrive_get_folder_tree": gdrive_get_folder_tree,
            "gdrive_create_folder": gdrive_create_folder,
            "gdrive_upload": gdrive_upload,
            "gdrive_move": gdrive_move,
            "gdrive_delete": gdrive_delete,
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
