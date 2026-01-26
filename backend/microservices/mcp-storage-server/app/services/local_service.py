"""
Local Filesystem Storage Service for MCP Storage Server.

Provides file storage operations using local filesystem.
For on-premise deployments without cloud storage.
"""

import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import mimetypes
import hashlib

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalStorageService:
    """
    Local filesystem storage service with multi-tenant support.

    Each tenant has their own directory for isolation.
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize local storage service.

        Args:
            base_path: Base directory for storage (uses settings if not provided)
        """
        self.base_path = Path(base_path or getattr(settings, 'local_storage_path', '/app/storage'))
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize the storage directory.

        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True

        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Local storage initialized at: {self.base_path}")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize local storage: {e}")
            return False

    def get_tenant_prefix(self, tenant_id: str, user_id: Optional[str] = None) -> str:
        """
        Get the storage prefix for a tenant.

        Args:
            tenant_id: Tenant identifier
            user_id: Optional user identifier for user-specific paths

        Returns:
            Path prefix for the tenant
        """
        if user_id:
            return f"tenant-{tenant_id}/user-{user_id}/"
        return f"tenant-{tenant_id}/"

    def _get_full_path(self, object_name: str, tenant_id: str, user_id: Optional[str] = None) -> Path:
        """Get the full filesystem path for an object."""
        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            relative_path = f"{prefix}{object_name}"
        else:
            relative_path = object_name
        return self.base_path / relative_path

    async def upload_file(
        self,
        content: bytes,
        object_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Upload file content to local filesystem.

        Args:
            content: File content as bytes
            object_name: Target object name (filename)
            tenant_id: Tenant identifier
            user_id: Optional user identifier
            content_type: Optional content type
            metadata: Optional metadata dict

        Returns:
            Upload result with object info
        """
        if not self._initialized:
            self.initialize()

        full_path = self._get_full_path(object_name, tenant_id, user_id)

        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        full_path.write_bytes(content)

        # Store metadata in sidecar file if provided
        if metadata:
            import json
            meta_path = full_path.with_suffix(full_path.suffix + '.meta')
            meta_path.write_text(json.dumps(metadata))

        prefix = self.get_tenant_prefix(tenant_id, user_id)
        relative_name = f"{prefix}{object_name}"

        logger.info(f"File uploaded: {relative_name} ({len(content)} bytes)")

        return {
            "object_name": relative_name,
            "size": len(content),
            "bucket": str(self.base_path),
            "content_type": content_type or mimetypes.guess_type(object_name)[0],
            "uploaded_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

    def download_file(
        self,
        object_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Download file content from local filesystem.

        Args:
            object_name: Object name to download
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            File content as bytes or None if not found
        """
        if not self._initialized:
            self.initialize()

        full_path = self._get_full_path(object_name, tenant_id, user_id)

        if not full_path.exists():
            logger.warning(f"File not found: {full_path}")
            return None

        content = full_path.read_bytes()
        logger.info(f"File downloaded: {full_path}")
        return content

    def delete_file(
        self,
        object_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Delete a file from local filesystem.

        Args:
            object_name: Object name to delete
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            True if deleted successfully
        """
        if not self._initialized:
            self.initialize()

        full_path = self._get_full_path(object_name, tenant_id, user_id)

        if not full_path.exists():
            logger.warning(f"File not found for deletion: {full_path}")
            return False

        full_path.unlink()

        # Also delete metadata file if exists
        meta_path = full_path.with_suffix(full_path.suffix + '.meta')
        if meta_path.exists():
            meta_path.unlink()

        logger.info(f"File deleted: {full_path}")
        return True

    def list_files(
        self,
        tenant_id: str,
        prefix: str = "",
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List files in a tenant's storage.

        Args:
            tenant_id: Tenant identifier
            prefix: Additional prefix to filter
            user_id: Optional user identifier
            limit: Maximum files to return

        Returns:
            List of file information dicts
        """
        if not self._initialized:
            self.initialize()

        tenant_prefix = self.get_tenant_prefix(tenant_id, user_id)
        search_path = self.base_path / tenant_prefix / prefix

        files = []
        if search_path.exists():
            for i, path in enumerate(search_path.rglob("*")):
                if i >= limit:
                    break
                if path.is_file() and not path.suffix == '.meta':
                    stat = path.stat()
                    relative_name = str(path.relative_to(self.base_path / tenant_prefix))

                    files.append({
                        "name": relative_name,
                        "full_path": str(path.relative_to(self.base_path)),
                        "size": stat.st_size,
                        "content_type": mimetypes.guess_type(str(path))[0],
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "metadata": self._load_metadata(path),
                    })

        logger.info(f"Listed {len(files)} files for tenant {tenant_id}")
        return files

    def _load_metadata(self, file_path: Path) -> Dict[str, str]:
        """Load metadata from sidecar file if exists."""
        meta_path = file_path.with_suffix(file_path.suffix + '.meta')
        if meta_path.exists():
            import json
            try:
                return json.loads(meta_path.read_text())
            except Exception:
                pass
        return {}

    def get_file_info(
        self,
        object_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get file metadata.

        Args:
            object_name: Object name
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            File info dict or None if not found
        """
        if not self._initialized:
            self.initialize()

        full_path = self._get_full_path(object_name, tenant_id, user_id)

        if not full_path.exists():
            return None

        stat = full_path.stat()
        prefix = self.get_tenant_prefix(tenant_id, user_id)

        return {
            "name": object_name,
            "full_path": str(full_path.relative_to(self.base_path)),
            "size": stat.st_size,
            "content_type": mimetypes.guess_type(str(full_path))[0],
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "metadata": self._load_metadata(full_path),
        }

    def generate_signed_url(
        self,
        object_name: str,
        tenant_id: str,
        method: str = "GET",
        expiration_seconds: Optional[int] = None,
        content_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Generate a signed URL for direct file access.

        For local storage, generates a token-based URL that can be validated.

        Args:
            object_name: Object name
            tenant_id: Tenant identifier
            method: HTTP method (GET, PUT)
            expiration_seconds: URL validity in seconds
            content_type: Content type for PUT
            user_id: Optional user identifier

        Returns:
            Tuple of (signed_url, expires_at_iso)
        """
        if not self._initialized:
            self.initialize()

        expiration = expiration_seconds or getattr(settings, 'signed_url_expiration', 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expiration)
        expires_ts = int(expires_at.timestamp())

        # Build full path for signing
        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            full_path = f"{prefix}{object_name}"
        else:
            full_path = object_name

        # Create a simple signature (in production, use a proper secret)
        secret = getattr(settings, 'signed_url_secret', 'local-storage-secret')
        signature_data = f"{method}:{full_path}:{expires_ts}:{secret}"
        signature = hashlib.sha256(signature_data.encode()).hexdigest()[:32]

        # Build URL (assumes a local endpoint that can validate and serve files)
        base_url = getattr(settings, 'local_storage_base_url', 'http://localhost:8000')
        url = f"{base_url}/storage/signed/{full_path}?expires={expires_ts}&sig={signature}&method={method}"

        if content_type and method.upper() == "PUT":
            url += f"&content_type={content_type}"

        logger.info(f"Generated signed URL for {full_path} ({method})")
        return url, expires_at.isoformat()

    def move_file(
        self,
        source_name: str,
        destination_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Move/rename a file.

        Args:
            source_name: Source object name
            destination_name: Destination object name
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            Move operation result
        """
        if not self._initialized:
            self.initialize()

        source_path = self._get_full_path(source_name, tenant_id, user_id)
        dest_path = self._get_full_path(destination_name, tenant_id, user_id)

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Move file
        shutil.move(str(source_path), str(dest_path))

        # Move metadata file if exists
        source_meta = source_path.with_suffix(source_path.suffix + '.meta')
        if source_meta.exists():
            dest_meta = dest_path.with_suffix(dest_path.suffix + '.meta')
            shutil.move(str(source_meta), str(dest_meta))

        logger.info(f"File moved: {source_path} -> {dest_path}")

        return {
            "source": source_name,
            "destination": destination_name,
            "bucket": str(self.base_path),
            "moved_at": datetime.utcnow().isoformat(),
        }

    def file_exists(
        self,
        object_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Check if a file exists.

        Args:
            object_name: Object name
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            True if file exists
        """
        if not self._initialized:
            self.initialize()

        full_path = self._get_full_path(object_name, tenant_id, user_id)
        return full_path.exists()


# Global service instance
_local_service: Optional[LocalStorageService] = None


def get_local_service(base_path: Optional[str] = None) -> LocalStorageService:
    """
    Get or create the local storage service singleton.

    Args:
        base_path: Optional base path

    Returns:
        LocalStorageService instance
    """
    global _local_service

    if _local_service is None:
        _local_service = LocalStorageService(base_path)
        _local_service.initialize()

    return _local_service
