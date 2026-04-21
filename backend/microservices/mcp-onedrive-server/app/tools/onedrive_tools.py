"""
OneDrive MCP Tools.

Provides MCP tools for interacting with OneDrive via Microsoft Graph API v1.0.
Each tool is designed to be used by AI agents through the MCP protocol.

Tools follow the naming convention: onedrive_{operation}

Configuration is loaded from the database using connector_id.
OAuth tokens are auto-refreshed when expired.
"""

import base64
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from ..core.config import get_connector, get_all_connectors
from ..services.onedrive_service import OneDriveService
from ..services.oauth_service import oauth_service

logger = logging.getLogger(__name__)

# Cache for service instances (keyed by connector_id)
_services: Dict[str, OneDriveService] = {}


async def _get_service(
    connector_id: str,
) -> OneDriveService:
    """Get or create OneDrive service with fresh token."""
    try:
        conn_uuid = UUID(connector_id)
    except ValueError as e:
        raise ValueError(f"Invalid UUID format: {e}")

    config = await get_connector(conn_uuid)
    if not config:
        raise ValueError(
            f"OneDrive connector not found or not active: {connector_id}"
        )

    if not config.is_authenticated:
        raise ValueError(
            f"Connector {connector_id} not authenticated. "
            "Please authorize via OAuth first."
        )

    # Ensure fresh access token
    access_token = await oauth_service.ensure_fresh_token(config)

    # Get or create service
    cache_key = str(config.connector_id)
    if cache_key in _services:
        old = _services[cache_key]
        await old.close()

    _services[cache_key] = OneDriveService(access_token, config)
    return _services[cache_key]


async def onedrive_list_connectors() -> Dict[str, Any]:
    """List all active OneDrive connectors."""
    try:
        connectors = await get_all_connectors()

        return {
            "success": True,
            "connectors": [
                {
                    "id": str(c.connector_id),
                    "name": c.name,
                    "description": c.description,
                    "drive_id": c.drive_id,
                    "folder_id": c.folder_id,
                    "microsoft_email": c.microsoft_email,
                    "authenticated": c.is_authenticated,
                }
                for c in connectors
            ],
        }
    except Exception as e:
        logger.error(f"onedrive_list_connectors failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_list_files(
    connector_id: str,
    folder_id: Optional[str] = None,
    include_subfolders: bool = False,
    max_results: int = 50,
) -> Dict[str, Any]:
    """List files in a OneDrive folder."""
    try:
        service = await _get_service(connector_id)
        config = service.config

        target_folder = folder_id or config.folder_id or "root"
        items = await service.list_items(
            folder_id=target_folder,
            include_subfolders=include_subfolders,
            max_results=min(max_results, 100),
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "folder_id": target_folder,
            "files": [
                {
                    "id": f.id,
                    "name": f.name,
                    "mime_type": f.mime_type,
                    "is_folder": f.is_folder,
                    "size_bytes": f.size_bytes,
                    "modified_at": f.modified_at.isoformat() if f.modified_at else None,
                    "web_url": f.web_url,
                }
                for f in items
            ],
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"onedrive_list_files failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_search(
    connector_id: str,
    query: str,
    folder_id: Optional[str] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """Search files in OneDrive by query."""
    try:
        service = await _get_service(connector_id)
        items = await service.search_items(
            query=query,
            folder_id=folder_id,
            max_results=min(max_results, 100),
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "query": query,
            "files": [
                {
                    "id": f.id,
                    "name": f.name,
                    "mime_type": f.mime_type,
                    "size_bytes": f.size_bytes,
                    "modified_at": f.modified_at.isoformat() if f.modified_at else None,
                    "web_url": f.web_url,
                }
                for f in items
            ],
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"onedrive_search failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_download(
    connector_id: str,
    file_id: str,
    return_base64: bool = True,
) -> Dict[str, Any]:
    """Download file content from OneDrive."""
    try:
        service = await _get_service(connector_id)

        # Get metadata first
        file_meta = await service.get_item_metadata(file_id)

        # Download content
        content, effective_mime = await service.download_item(file_id)

        result = {
            "success": True,
            "connector_id": connector_id,
            "filename": file_meta.name,
            "mime_type": effective_mime,
            "size_bytes": len(content),
        }

        if return_base64:
            result["content_base64"] = base64.b64encode(content).decode("utf-8")

        return result
    except Exception as e:
        logger.error(f"onedrive_download failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_get_metadata(
    connector_id: str,
    file_id: str,
) -> Dict[str, Any]:
    """Get detailed metadata for a file."""
    try:
        service = await _get_service(connector_id)
        item = await service.get_item_metadata(file_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "file": {
                "id": item.id,
                "name": item.name,
                "mime_type": item.mime_type,
                "is_folder": item.is_folder,
                "size_bytes": item.size_bytes,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "modified_at": item.modified_at.isoformat() if item.modified_at else None,
                "web_url": item.web_url,
                "parent_path": item.parent_path,
                "drive_id": item.drive_id,
            },
        }
    except Exception as e:
        logger.error(f"onedrive_get_metadata failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_get_folder_tree(
    connector_id: str,
    folder_id: Optional[str] = None,
    max_depth: int = 3,
) -> Dict[str, Any]:
    """Get folder tree structure."""
    try:
        service = await _get_service(connector_id)
        target_folder = folder_id or service.config.folder_id or "root"
        tree = await service.get_folder_tree(target_folder, max_depth=max_depth)

        return {
            "success": True,
            "connector_id": connector_id,
            "tree": tree,
        }
    except Exception as e:
        logger.error(f"onedrive_get_folder_tree failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_create_folder(
    connector_id: str,
    name: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new folder in OneDrive."""
    try:
        service = await _get_service(connector_id)
        folder = await service.create_folder(name, parent_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "web_url": folder.web_url,
            },
        }
    except Exception as e:
        logger.error(f"onedrive_create_folder failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_upload(
    connector_id: str,
    filename: str,
    content_base64: str,
    mime_type: str = "application/octet-stream",
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a file to OneDrive."""
    try:
        service = await _get_service(connector_id)
        content = base64.b64decode(content_base64)

        item = await service.upload_item(
            name=filename,
            content=content,
            parent_id=parent_id,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "file": {
                "id": item.id,
                "name": item.name,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "web_url": item.web_url,
            },
        }
    except Exception as e:
        logger.error(f"onedrive_upload failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_move(
    connector_id: str,
    file_id: str,
    target_folder_id: str,
) -> Dict[str, Any]:
    """Move an item to a different folder."""
    try:
        service = await _get_service(connector_id)
        item = await service.move_item(file_id, target_folder_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "file": {
                "id": item.id,
                "name": item.name,
                "parent_path": item.parent_path,
            },
        }
    except Exception as e:
        logger.error(f"onedrive_move failed: {e}")
        return {"success": False, "error": str(e)}


async def onedrive_delete(
    connector_id: str,
    file_id: str,
    permanent: bool = False,
) -> Dict[str, Any]:
    """Delete (recycle) an item from OneDrive."""
    try:
        service = await _get_service(connector_id)
        await service.delete_item(file_id, permanent=permanent)

        return {
            "success": True,
            "connector_id": connector_id,
            "file_id": file_id,
            "permanent": permanent,
        }
    except Exception as e:
        logger.error(f"onedrive_delete failed: {e}")
        return {"success": False, "error": str(e)}
