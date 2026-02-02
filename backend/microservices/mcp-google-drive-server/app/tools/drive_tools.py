"""
Google Drive MCP Tools.

Provides MCP tools for interacting with Google Drive API v3.
Each tool is designed to be used by AI agents through the MCP protocol.

Tools follow the naming convention: gdrive_{operation}

Configuration is loaded from the database using connector_id and tenant_id.
OAuth tokens are auto-refreshed when expired.
"""

import base64
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from ..core.config import get_connector, get_connectors_for_tenant
from ..services.drive_service import DriveService
from ..services.oauth_service import oauth_service

logger = logging.getLogger(__name__)

# Cache for service instances (keyed by connector_id)
_services: Dict[str, DriveService] = {}


async def _get_service(
    connector_id: str,
    tenant_id: str,
) -> DriveService:
    """Get or create Drive service with fresh token."""
    try:
        conn_uuid = UUID(connector_id)
        tenant_uuid = UUID(tenant_id)
    except ValueError as e:
        raise ValueError(f"Invalid UUID format: {e}")

    config = await get_connector(conn_uuid, tenant_uuid)
    if not config:
        raise ValueError(
            f"Google Drive connector not found or not active: {connector_id}"
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

    _services[cache_key] = DriveService(access_token, config)
    return _services[cache_key]


async def gdrive_list_connectors(
    tenant_id: str,
) -> Dict[str, Any]:
    """List all active Google Drive connectors for a tenant."""
    try:
        tenant_uuid = UUID(tenant_id)
        connectors = await get_connectors_for_tenant(tenant_uuid)

        return {
            "success": True,
            "tenant_id": tenant_id,
            "connectors": [
                {
                    "id": str(c.connector_id),
                    "name": c.name,
                    "description": c.description,
                    "folder_id": c.folder_id,
                    "google_email": c.google_email,
                    "authenticated": c.is_authenticated,
                }
                for c in connectors
            ],
        }
    except Exception as e:
        logger.error(f"gdrive_list_connectors failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_list_files(
    connector_id: str,
    tenant_id: str,
    folder_id: Optional[str] = None,
    include_subfolders: bool = False,
    max_results: int = 50,
) -> Dict[str, Any]:
    """List files in a Google Drive folder."""
    try:
        service = await _get_service(connector_id, tenant_id)
        config = service.config

        target_folder = folder_id or config.folder_id or "root"
        files = await service.list_files(
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
                    "web_view_link": f.web_view_link,
                }
                for f in files
            ],
            "count": len(files),
        }
    except Exception as e:
        logger.error(f"gdrive_list_files failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_search(
    connector_id: str,
    tenant_id: str,
    query: str,
    folder_id: Optional[str] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """Search files in Google Drive by full-text query."""
    try:
        service = await _get_service(connector_id, tenant_id)
        files = await service.search_files(
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
                    "web_view_link": f.web_view_link,
                }
                for f in files
            ],
            "count": len(files),
        }
    except Exception as e:
        logger.error(f"gdrive_search failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_download(
    connector_id: str,
    tenant_id: str,
    file_id: str,
    return_base64: bool = True,
) -> Dict[str, Any]:
    """Download file content from Google Drive."""
    try:
        service = await _get_service(connector_id, tenant_id)

        # Get metadata first
        file_meta = await service.get_file_metadata(file_id)

        # Download content
        content, effective_mime = await service.download_file(
            file_id, file_meta.mime_type
        )

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
        logger.error(f"gdrive_download failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_get_metadata(
    connector_id: str,
    tenant_id: str,
    file_id: str,
) -> Dict[str, Any]:
    """Get detailed metadata for a file."""
    try:
        service = await _get_service(connector_id, tenant_id)
        file = await service.get_file_metadata(file_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "file": {
                "id": file.id,
                "name": file.name,
                "mime_type": file.mime_type,
                "is_folder": file.is_folder,
                "size_bytes": file.size_bytes,
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "modified_at": file.modified_at.isoformat() if file.modified_at else None,
                "web_view_link": file.web_view_link,
                "parents": file.parents,
                "owners": file.owners,
            },
        }
    except Exception as e:
        logger.error(f"gdrive_get_metadata failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_get_folder_tree(
    connector_id: str,
    tenant_id: str,
    folder_id: Optional[str] = None,
    max_depth: int = 3,
) -> Dict[str, Any]:
    """Get folder tree structure."""
    try:
        service = await _get_service(connector_id, tenant_id)
        target_folder = folder_id or service.config.folder_id or "root"
        tree = await service.get_folder_tree(target_folder, max_depth=max_depth)

        return {
            "success": True,
            "connector_id": connector_id,
            "tree": tree,
        }
    except Exception as e:
        logger.error(f"gdrive_get_folder_tree failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_create_folder(
    connector_id: str,
    tenant_id: str,
    name: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new folder in Google Drive."""
    try:
        service = await _get_service(connector_id, tenant_id)
        folder = await service.create_folder(name, parent_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "web_view_link": folder.web_view_link,
            },
        }
    except Exception as e:
        logger.error(f"gdrive_create_folder failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_upload(
    connector_id: str,
    tenant_id: str,
    filename: str,
    content_base64: str,
    mime_type: str = "application/octet-stream",
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a file to Google Drive."""
    try:
        service = await _get_service(connector_id, tenant_id)
        content = base64.b64decode(content_base64)

        file = await service.upload_file(
            name=filename,
            content=content,
            mime_type=mime_type,
            parent_id=parent_id,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "file": {
                "id": file.id,
                "name": file.name,
                "mime_type": file.mime_type,
                "size_bytes": file.size_bytes,
                "web_view_link": file.web_view_link,
            },
        }
    except Exception as e:
        logger.error(f"gdrive_upload failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_move(
    connector_id: str,
    tenant_id: str,
    file_id: str,
    target_folder_id: str,
) -> Dict[str, Any]:
    """Move a file to a different folder."""
    try:
        service = await _get_service(connector_id, tenant_id)
        file = await service.move_file(file_id, target_folder_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "file": {
                "id": file.id,
                "name": file.name,
                "parents": file.parents,
            },
        }
    except Exception as e:
        logger.error(f"gdrive_move failed: {e}")
        return {"success": False, "error": str(e)}


async def gdrive_delete(
    connector_id: str,
    tenant_id: str,
    file_id: str,
    permanent: bool = False,
) -> Dict[str, Any]:
    """Delete (trash) or permanently delete a file."""
    try:
        service = await _get_service(connector_id, tenant_id)
        await service.delete_file(file_id, permanent=permanent)

        return {
            "success": True,
            "connector_id": connector_id,
            "file_id": file_id,
            "permanent": permanent,
        }
    except Exception as e:
        logger.error(f"gdrive_delete failed: {e}")
        return {"success": False, "error": str(e)}
