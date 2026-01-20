"""
MCP Storage Tools Implementation.

These functions are registered as MCP tools and can be called by clients.
Each tool has a clear docstring that serves as the tool description for LLMs.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

from app.services.gcs_service import get_gcs_service

logger = logging.getLogger(__name__)


async def upload_file(
    content_base64: str,
    filename: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    content_type: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Upload a file to the tenant's storage bucket.

    Use this tool when you need to save a file to cloud storage.
    The file content should be provided as base64-encoded string.

    Args:
        content_base64: File content encoded as base64 string
        filename: Name for the uploaded file (e.g., "report.pdf")
        tenant_id: Tenant identifier for storage isolation
        user_id: Optional user identifier for user-specific storage
        content_type: Optional MIME type (e.g., "application/pdf")
        metadata: Optional key-value metadata to attach to the file

    Returns:
        Upload result with:
        - object_name: Full path in storage
        - size: File size in bytes
        - bucket: Bucket name
        - uploaded_at: Upload timestamp
    """
    try:
        # Decode base64 content
        content = base64.b64decode(content_base64)

        service = get_gcs_service()
        result = await service.upload_file(
            content=content,
            object_name=filename,
            tenant_id=tenant_id,
            user_id=user_id,
            content_type=content_type,
            metadata=metadata,
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "filename": filename,
        }


async def download_file(
    filename: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    return_base64: bool = True,
) -> Dict[str, Any]:
    """
    Download a file from the tenant's storage.

    Use this tool when you need to retrieve file content from storage.
    The content is returned as base64-encoded string by default.

    Args:
        filename: Name of the file to download
        tenant_id: Tenant identifier
        user_id: Optional user identifier
        return_base64: If True, return content as base64 (default). If False, return raw text.

    Returns:
        Download result with:
        - content: File content (base64 or text depending on return_base64)
        - filename: Requested filename
        - size: Content size in bytes
        - encoding: "base64" or "text"
    """
    try:
        service = get_gcs_service()
        content = service.download_file(
            object_name=filename,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if content is None:
            return {
                "success": False,
                "error": "File not found",
                "filename": filename,
            }

        if return_base64:
            encoded_content = base64.b64encode(content).decode("utf-8")
            return {
                "success": True,
                "content": encoded_content,
                "filename": filename,
                "size": len(content),
                "encoding": "base64",
            }
        else:
            # Try to decode as text
            try:
                text_content = content.decode("utf-8")
            except UnicodeDecodeError:
                text_content = content.decode("latin-1")

            return {
                "success": True,
                "content": text_content,
                "filename": filename,
                "size": len(content),
                "encoding": "text",
            }

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "filename": filename,
        }


async def list_files(
    tenant_id: str,
    prefix: str = "",
    user_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List files in the tenant's storage.

    Use this tool when you need to see what files are available in storage.
    You can filter by prefix to list files in a specific "directory".

    Args:
        tenant_id: Tenant identifier
        prefix: Optional prefix to filter files (e.g., "documents/" to list only in documents folder)
        user_id: Optional user identifier for user-specific listing
        limit: Maximum number of files to return (default 100)

    Returns:
        List result with:
        - files: List of file objects with name, size, type, created, updated
        - count: Number of files returned
        - prefix: The prefix used for filtering
    """
    try:
        service = get_gcs_service()
        files = service.list_files(
            tenant_id=tenant_id,
            prefix=prefix,
            user_id=user_id,
            limit=limit,
        )

        return {
            "success": True,
            "files": files,
            "count": len(files),
            "prefix": prefix,
            "tenant_id": tenant_id,
        }

    except Exception as e:
        logger.error(f"List files failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "files": [],
            "count": 0,
        }


async def delete_file(
    filename: str,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Delete a file from the tenant's storage.

    Use this tool when you need to remove a file from storage.
    This operation is permanent and cannot be undone.

    Args:
        filename: Name of the file to delete
        tenant_id: Tenant identifier
        user_id: Optional user identifier

    Returns:
        Delete result with:
        - deleted: True if file was deleted
        - filename: The deleted filename
    """
    try:
        service = get_gcs_service()
        deleted = service.delete_file(
            object_name=filename,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if deleted:
            return {
                "success": True,
                "deleted": True,
                "filename": filename,
            }
        else:
            return {
                "success": False,
                "error": "File not found",
                "deleted": False,
                "filename": filename,
            }

    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "deleted": False,
            "filename": filename,
        }


async def get_file_info(
    filename: str,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get information about a file without downloading its content.

    Use this tool when you need to check file metadata like size,
    content type, or creation date without retrieving the actual content.

    Args:
        filename: Name of the file
        tenant_id: Tenant identifier
        user_id: Optional user identifier

    Returns:
        File info with:
        - name: Filename
        - size: File size in bytes
        - content_type: MIME type
        - created: Creation timestamp
        - updated: Last modification timestamp
        - metadata: Custom metadata dict
    """
    try:
        service = get_gcs_service()
        info = service.get_file_info(
            object_name=filename,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if info is None:
            return {
                "success": False,
                "error": "File not found",
                "filename": filename,
            }

        return {
            "success": True,
            **info
        }

    except Exception as e:
        logger.error(f"Get file info failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "filename": filename,
        }


async def generate_signed_url(
    filename: str,
    tenant_id: str,
    method: str = "GET",
    expiration_seconds: int = 3600,
    content_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a signed URL for direct file access.

    Use this tool when you need to provide temporary access to a file
    without going through the storage service. Useful for large file
    downloads or allowing external systems to upload.

    Args:
        filename: Name of the file
        tenant_id: Tenant identifier
        method: HTTP method - "GET" for download, "PUT" for upload (default: GET)
        expiration_seconds: URL validity in seconds (default: 3600 = 1 hour)
        content_type: Required for PUT - the expected content type
        user_id: Optional user identifier

    Returns:
        Signed URL result with:
        - url: The signed URL for direct access
        - expires_at: ISO timestamp when URL expires
        - method: The HTTP method allowed
    """
    try:
        service = get_gcs_service()
        url, expires_at = service.generate_signed_url(
            object_name=filename,
            tenant_id=tenant_id,
            method=method.upper(),
            expiration_seconds=expiration_seconds,
            content_type=content_type,
            user_id=user_id,
        )

        return {
            "success": True,
            "url": url,
            "expires_at": expires_at,
            "method": method.upper(),
            "filename": filename,
        }

    except Exception as e:
        logger.error(f"Generate signed URL failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "filename": filename,
        }


async def move_file(
    source: str,
    destination: str,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Move or rename a file within the tenant's storage.

    Use this tool when you need to rename a file or move it to a
    different location within the same tenant's storage.

    Args:
        source: Current filename/path
        destination: New filename/path
        tenant_id: Tenant identifier
        user_id: Optional user identifier

    Returns:
        Move result with:
        - source: Original filename
        - destination: New filename
        - moved_at: Timestamp of the move operation
    """
    try:
        service = get_gcs_service()
        result = service.move_file(
            source_name=source,
            destination_name=destination,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return {
            "success": True,
            **result
        }

    except FileNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "source": source,
            "destination": destination,
        }
    except Exception as e:
        logger.error(f"Move file failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "source": source,
            "destination": destination,
        }


async def file_exists(
    filename: str,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check if a file exists in storage.

    Use this tool when you need to verify if a file exists before
    attempting to download or process it.

    Args:
        filename: Name of the file to check
        tenant_id: Tenant identifier
        user_id: Optional user identifier

    Returns:
        Existence check with:
        - exists: True if file exists, False otherwise
        - filename: The checked filename
    """
    try:
        service = get_gcs_service()
        exists = service.file_exists(
            object_name=filename,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return {
            "success": True,
            "exists": exists,
            "filename": filename,
        }

    except Exception as e:
        logger.error(f"File exists check failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "exists": False,
            "filename": filename,
        }
