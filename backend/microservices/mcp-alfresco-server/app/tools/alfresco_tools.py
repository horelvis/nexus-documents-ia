"""
Alfresco MCP Tools.

Provides MCP tools for interacting with Alfresco 7.x ECM.
Each tool is designed to be used by AI agents through the MCP protocol.

Tools follow the naming convention: alfresco_{operation}

Configuration is loaded from the database using connector_id.
"""

import base64
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from ..core.config import get_connector, get_all_connectors
from ..services.alfresco_service import AlfrescoService

logger = logging.getLogger(__name__)

# Cache for service instances (keyed by connector_id)
_services: Dict[str, AlfrescoService] = {}


async def _get_service(
    connector_id: str,
) -> AlfrescoService:
    """
    Get or create Alfresco service for a connector.

    Args:
        connector_id: Connector UUID (from database)

    Returns:
        AlfrescoService instance
    """
    # Parse UUID
    try:
        conn_uuid = UUID(connector_id)
    except ValueError as e:
        raise ValueError(f"Invalid UUID format: {e}")

    # Load connector config from database
    config = await get_connector(conn_uuid)
    if not config:
        raise ValueError(
            f"Alfresco connector not found or not active: {connector_id}"
        )

    # Get or create service
    cache_key = str(config.connector_id)
    if cache_key not in _services:
        _services[cache_key] = AlfrescoService(config)
    else:
        # Update config if changed (cache may have new config)
        existing = _services[cache_key]
        if existing.config.url != config.url:
            # Config changed, recreate service
            await existing.close()
            _services[cache_key] = AlfrescoService(config)

    return _services[cache_key]


async def alfresco_search(
    connector_id: str,
    query: str,
    skip: int = 0,
    max_items: int = 50,
    node_type: Optional[str] = None,
    site_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search documents in Alfresco using AFTS (Alfresco Full Text Search).
    """
    try:
        service = await _get_service(connector_id)
        result = await service.search(
            query=query,
            skip=skip,
            max_items=min(max_items, 100),
            node_type=node_type,
            site_id=site_id,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.node_type,
                    "is_folder": n.is_folder,
                    "is_file": n.is_file,
                    "mime_type": n.mime_type,
                    "size_bytes": n.content_size,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                    "modified_at": n.modified_at.isoformat() if n.modified_at else None,
                    "created_by": n.created_by,
                    "modified_by": n.modified_by,
                    "path": n.path,
                }
                for n in result.nodes
            ],
            "pagination": {
                "total": result.total,
                "has_more": result.has_more,
                "skip": result.skip,
                "max_items": result.max_items,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco search failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_download(
    connector_id: str,
    node_id: str,
    version_id: Optional[str] = None,
    return_base64: bool = True,
) -> Dict[str, Any]:
    """Download document content from Alfresco."""
    try:
        service = await _get_service(connector_id)
        content, filename, mime_type = await service.download_content(
            node_id=node_id,
            version_id=version_id,
        )

        result = {
            "success": True,
            "connector_id": connector_id,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
        }

        if return_base64:
            result["content_base64"] = base64.b64encode(content).decode("utf-8")
        else:
            # Return raw bytes (for binary handling)
            result["content"] = content

        return result
    except Exception as e:
        logger.error(f"Alfresco download failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_upload(
    connector_id: str,
    parent_id: str,
    filename: str,
    content_base64: str,
    mime_type: Optional[str] = None,
    overwrite: bool = False,
    title: Optional[str] = None,
    description: Optional[str] = None,
    major_version: bool = True,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a new document to Alfresco."""
    try:
        service = await _get_service(connector_id)

        # Decode base64 content
        content = base64.b64decode(content_base64)

        # Build properties
        properties = {}
        if title:
            properties["cm:title"] = title
        if description:
            properties["cm:description"] = description

        node = await service.upload_content(
            parent_id=parent_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
            overwrite=overwrite,
            properties=properties if properties else None,
            major_version=major_version,
            comment=comment,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "node": {
                "id": node.id,
                "name": node.name,
                "type": node.node_type,
                "mime_type": node.mime_type,
                "size_bytes": node.content_size,
                "created_at": node.created_at.isoformat() if node.created_at else None,
                "path": node.path,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco upload failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_list(
    connector_id: str,
    folder_id: str = "-root-",
    skip: int = 0,
    max_items: int = 50,
    files_only: bool = False,
    folders_only: bool = False,
    order_by: str = "name ASC",
) -> Dict[str, Any]:
    """List contents of a folder in Alfresco."""
    try:
        service = await _get_service(connector_id)

        # Build where clause for filtering
        where = None
        if files_only:
            where = "(isFile=true)"
        elif folders_only:
            where = "(isFolder=true)"

        result = await service.list_children(
            folder_id=folder_id,
            skip=skip,
            max_items=min(max_items, 100),
            where=where,
            order_by=order_by,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "folder_id": folder_id,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.node_type,
                    "is_folder": n.is_folder,
                    "is_file": n.is_file,
                    "mime_type": n.mime_type,
                    "size_bytes": n.content_size,
                    "modified_at": n.modified_at.isoformat() if n.modified_at else None,
                    "modified_by": n.modified_by,
                }
                for n in result.nodes
            ],
            "pagination": {
                "total": result.total,
                "has_more": result.has_more,
                "skip": result.skip,
                "max_items": result.max_items,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco list failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_get_metadata(
    connector_id: str,
    node_id: str,
    include_path: bool = True,
) -> Dict[str, Any]:
    """Get detailed metadata for a node."""
    try:
        service = await _get_service(connector_id)
        node = await service.get_node(node_id, include_path=include_path)

        return {
            "success": True,
            "connector_id": connector_id,
            "node": {
                "id": node.id,
                "name": node.name,
                "type": node.node_type,
                "is_folder": node.is_folder,
                "is_file": node.is_file,
                "mime_type": node.mime_type,
                "size_bytes": node.content_size,
                "created_at": node.created_at.isoformat() if node.created_at else None,
                "modified_at": node.modified_at.isoformat() if node.modified_at else None,
                "created_by": node.created_by,
                "modified_by": node.modified_by,
                "parent_id": node.parent_id,
                "path": node.path,
                "properties": node.properties,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco get_metadata failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_get_versions(
    connector_id: str,
    node_id: str,
    skip: int = 0,
    max_items: int = 20,
) -> Dict[str, Any]:
    """Get version history for a document."""
    try:
        service = await _get_service(connector_id)
        versions = await service.get_versions(
            node_id=node_id,
            skip=skip,
            max_items=max_items,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "node_id": node_id,
            "versions": [
                {
                    "id": v.id,
                    "label": v.version_label,
                    "is_major": v.is_major,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "created_by": v.created_by,
                    "size_bytes": v.content_size,
                    "comment": v.comment,
                }
                for v in versions
            ],
        }
    except Exception as e:
        logger.error(f"Alfresco get_versions failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_move(
    connector_id: str,
    node_id: str,
    target_folder_id: str,
    new_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Move a node to a different folder."""
    try:
        service = await _get_service(connector_id)
        node = await service.move_node(
            node_id=node_id,
            target_parent_id=target_folder_id,
            new_name=new_name,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "node": {
                "id": node.id,
                "name": node.name,
                "parent_id": node.parent_id,
                "path": node.path,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco move failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_copy(
    connector_id: str,
    node_id: str,
    target_folder_id: str,
    new_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Copy a node to a folder."""
    try:
        service = await _get_service(connector_id)
        node = await service.copy_node(
            node_id=node_id,
            target_parent_id=target_folder_id,
            new_name=new_name,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "node": {
                "id": node.id,
                "name": node.name,
                "parent_id": node.parent_id,
                "path": node.path,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco copy failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_delete(
    connector_id: str,
    node_id: str,
    permanent: bool = False,
) -> Dict[str, Any]:
    """Delete a node."""
    try:
        service = await _get_service(connector_id)
        await service.delete_node(node_id=node_id, permanent=permanent)

        return {
            "success": True,
            "connector_id": connector_id,
            "node_id": node_id,
            "permanent": permanent,
        }
    except Exception as e:
        logger.error(f"Alfresco delete failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_update_metadata(
    connector_id: str,
    node_id: str,
    properties: Dict[str, Any],
    new_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Update node properties/metadata."""
    try:
        service = await _get_service(connector_id)
        node = await service.update_properties(
            node_id=node_id,
            properties=properties,
            name=new_name,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "node": {
                "id": node.id,
                "name": node.name,
                "properties": node.properties,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco update_metadata failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_create_folder(
    connector_id: str,
    parent_id: str,
    name: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new folder."""
    try:
        service = await _get_service(connector_id)
        node = await service.create_folder(
            parent_id=parent_id,
            name=name,
            title=title,
            description=description,
        )

        return {
            "success": True,
            "connector_id": connector_id,
            "node": {
                "id": node.id,
                "name": node.name,
                "type": node.node_type,
                "path": node.path,
            },
        }
    except Exception as e:
        logger.error(f"Alfresco create_folder failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_get_sites(
    connector_id: str,
    skip: int = 0,
    max_items: int = 50,
) -> Dict[str, Any]:
    """List available Alfresco sites."""
    try:
        service = await _get_service(connector_id)
        sites = await service.get_sites(skip=skip, max_items=max_items)

        return {
            "success": True,
            "connector_id": connector_id,
            "sites": [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                    "visibility": s.get("visibility"),
                    "role": s.get("role"),
                }
                for s in sites
            ],
        }
    except Exception as e:
        logger.error(f"Alfresco get_sites failed: {e}")
        return {"success": False, "error": str(e)}


async def alfresco_list_connectors() -> Dict[str, Any]:
    """
    List all active Alfresco connectors.

    This tool helps discover which Alfresco instances are available.
    """
    try:
        connectors = await get_all_connectors()

        return {
            "success": True,
            "connectors": [
                {
                    "id": str(c.connector_id),
                    "name": c.name,
                    "description": c.description,
                    "url": c.url,
                    "default_site_id": c.default_site_id,
                }
                for c in connectors
            ],
        }
    except Exception as e:
        logger.error(f"Alfresco list_connectors failed: {e}")
        return {"success": False, "error": str(e)}
