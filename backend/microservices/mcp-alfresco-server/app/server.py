"""
MCP Server for Alfresco 7.x ECM.

Exposes Alfresco document management operations as MCP tools.
Configuration is loaded from the database using connector_id and tenant_id.
"""

import logging
from typing import Any, Dict

from mcp.server import Server
from mcp.types import Tool, TextContent

from .tools.alfresco_tools import (
    alfresco_search,
    alfresco_download,
    alfresco_upload,
    alfresco_list,
    alfresco_get_metadata,
    alfresco_get_versions,
    alfresco_move,
    alfresco_copy,
    alfresco_delete,
    alfresco_update_metadata,
    alfresco_create_folder,
    alfresco_get_sites,
    alfresco_list_connectors,
)

logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server with Alfresco tools."""

    server = Server("alfresco")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return list of available Alfresco tools."""
        return [
            Tool(
                name="alfresco_list_connectors",
                description=(
                    "List all active Alfresco connectors configured for the tenant. "
                    "Use this first to discover available Alfresco instances."
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
                name="alfresco_search",
                description=(
                    "Search documents in Alfresco using AFTS (Alfresco Full Text Search). "
                    "Supports full-text search, property filters, wildcards, and boolean operators. "
                    "Examples: 'financial report 2024', 'cm:name:budget.pdf', 'contract AND signed'"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID (from alfresco_list_connectors)",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "query": {
                            "type": "string",
                            "description": "AFTS search query string",
                        },
                        "skip": {
                            "type": "integer",
                            "description": "Number of results to skip (pagination)",
                            "default": 0,
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 50,
                        },
                        "node_type": {
                            "type": "string",
                            "description": "Filter by type: 'cm:content' (files) or 'cm:folder'",
                        },
                        "site_id": {
                            "type": "string",
                            "description": "Restrict search to a specific site",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "query"],
                },
            ),
            Tool(
                name="alfresco_download",
                description=(
                    "Download document content from Alfresco. "
                    "Returns the file content as base64, along with filename and MIME type."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Document node ID (UUID)",
                        },
                        "version_id": {
                            "type": "string",
                            "description": "Specific version ID to download",
                        },
                        "return_base64": {
                            "type": "boolean",
                            "description": "Return content as base64 string",
                            "default": True,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id"],
                },
            ),
            Tool(
                name="alfresco_upload",
                description=(
                    "Upload a new document to Alfresco. "
                    "Content must be provided as base64-encoded string."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "Parent folder ID (use '-root-' for Company Home)",
                        },
                        "filename": {
                            "type": "string",
                            "description": "Name for the new document",
                        },
                        "content_base64": {
                            "type": "string",
                            "description": "File content as base64 string",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "MIME type (auto-detected if not provided)",
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "Update existing file with same name",
                            "default": False,
                        },
                        "title": {
                            "type": "string",
                            "description": "Document title (cm:title)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Document description",
                        },
                        "major_version": {
                            "type": "boolean",
                            "description": "Create major version (1.0)",
                            "default": True,
                        },
                        "comment": {
                            "type": "string",
                            "description": "Version comment",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "parent_id", "filename", "content_base64"],
                },
            ),
            Tool(
                name="alfresco_list",
                description=(
                    "List contents of a folder in Alfresco. "
                    "Returns files and folders with metadata."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "folder_id": {
                            "type": "string",
                            "description": "Folder ID (use '-root-' for Company Home)",
                            "default": "-root-",
                        },
                        "skip": {
                            "type": "integer",
                            "description": "Number of results to skip",
                            "default": 0,
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 50,
                        },
                        "files_only": {
                            "type": "boolean",
                            "description": "Only return files",
                            "default": False,
                        },
                        "folders_only": {
                            "type": "boolean",
                            "description": "Only return folders",
                            "default": False,
                        },
                        "order_by": {
                            "type": "string",
                            "description": "Sort order (e.g., 'name ASC', 'modifiedAt DESC')",
                            "default": "name ASC",
                        },
                    },
                    "required": ["connector_id", "tenant_id"],
                },
            ),
            Tool(
                name="alfresco_get_metadata",
                description=(
                    "Get detailed metadata for a node, including all properties."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Node ID (UUID)",
                        },
                        "include_path": {
                            "type": "boolean",
                            "description": "Include full path information",
                            "default": True,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id"],
                },
            ),
            Tool(
                name="alfresco_get_versions",
                description=(
                    "Get version history for a document. "
                    "Shows all versions with labels, dates, and comments."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Document node ID",
                        },
                        "skip": {
                            "type": "integer",
                            "description": "Versions to skip",
                            "default": 0,
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Max versions to return",
                            "default": 20,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id"],
                },
            ),
            Tool(
                name="alfresco_move",
                description="Move a node (file or folder) to a different folder.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Node ID to move",
                        },
                        "target_folder_id": {
                            "type": "string",
                            "description": "Destination folder ID",
                        },
                        "new_name": {
                            "type": "string",
                            "description": "New name (optional)",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id", "target_folder_id"],
                },
            ),
            Tool(
                name="alfresco_copy",
                description="Copy a node (file or folder) to a folder.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Node ID to copy",
                        },
                        "target_folder_id": {
                            "type": "string",
                            "description": "Destination folder ID",
                        },
                        "new_name": {
                            "type": "string",
                            "description": "Name for the copy (optional)",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id", "target_folder_id"],
                },
            ),
            Tool(
                name="alfresco_delete",
                description=(
                    "Delete a node. By default, moves to trash bin. "
                    "Use permanent=true to permanently delete."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Node ID to delete",
                        },
                        "permanent": {
                            "type": "boolean",
                            "description": "Permanently delete (skip trash)",
                            "default": False,
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id"],
                },
            ),
            Tool(
                name="alfresco_update_metadata",
                description=(
                    "Update node properties/metadata. "
                    "Common properties: cm:title, cm:description, cm:author"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "node_id": {
                            "type": "string",
                            "description": "Node ID",
                        },
                        "properties": {
                            "type": "object",
                            "description": "Property key-value pairs",
                        },
                        "new_name": {
                            "type": "string",
                            "description": "New name for the node",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "node_id", "properties"],
                },
            ),
            Tool(
                name="alfresco_create_folder",
                description="Create a new folder in Alfresco.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "parent_id": {
                            "type": "string",
                            "description": "Parent folder ID (use '-root-' for Company Home)",
                        },
                        "name": {
                            "type": "string",
                            "description": "Folder name",
                        },
                        "title": {
                            "type": "string",
                            "description": "Folder title (cm:title)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Folder description",
                        },
                    },
                    "required": ["connector_id", "tenant_id", "parent_id", "name"],
                },
            ),
            Tool(
                name="alfresco_get_sites",
                description=(
                    "List available Alfresco sites. "
                    "Sites are collaborative workspaces containing document libraries."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "connector_id": {
                            "type": "string",
                            "description": "Alfresco connector UUID",
                        },
                        "tenant_id": {
                            "type": "string",
                            "description": "Tenant UUID",
                        },
                        "skip": {
                            "type": "integer",
                            "description": "Sites to skip",
                            "default": 0,
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Max sites to return",
                            "default": 50,
                        },
                    },
                    "required": ["connector_id", "tenant_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> list[TextContent]:
        """Execute an Alfresco tool and return results."""
        import json

        logger.info(f"Executing tool: {name}")

        # Map tool names to functions
        tools = {
            "alfresco_list_connectors": alfresco_list_connectors,
            "alfresco_search": alfresco_search,
            "alfresco_download": alfresco_download,
            "alfresco_upload": alfresco_upload,
            "alfresco_list": alfresco_list,
            "alfresco_get_metadata": alfresco_get_metadata,
            "alfresco_get_versions": alfresco_get_versions,
            "alfresco_move": alfresco_move,
            "alfresco_copy": alfresco_copy,
            "alfresco_delete": alfresco_delete,
            "alfresco_update_metadata": alfresco_update_metadata,
            "alfresco_create_folder": alfresco_create_folder,
            "alfresco_get_sites": alfresco_get_sites,
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
