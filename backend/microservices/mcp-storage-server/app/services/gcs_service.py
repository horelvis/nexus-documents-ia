"""
Google Cloud Storage Service for MCP Storage Server.

Provides all GCS operations used by MCP tools.
Based on the original storage-service implementation.
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from google.cloud import storage
from google.oauth2 import service_account

from app.core.config import settings

logger = logging.getLogger(__name__)


class GCSService:
    """
    Google Cloud Storage service with multi-tenant support.

    Each tenant has their own bucket or prefix isolation.
    """

    def __init__(self, bucket_name: Optional[str] = None):
        """
        Initialize GCS service.

        Args:
            bucket_name: Bucket name (uses default if not provided)
        """
        self.bucket_name = bucket_name or settings.gcs_default_bucket
        self.client: Optional[storage.Client] = None
        self.bucket: Optional[storage.Bucket] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize the GCS client and bucket.

        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True

        try:
            self._init_client()
            self._ensure_bucket_exists()
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize GCS service: {e}")
            return False

    def _init_client(self):
        """Initialize the GCS client."""
        logger.info(f"Initializing GCS client for bucket: {self.bucket_name}")

        if settings.gcs_credentials and settings.gcs_credentials.strip():
            if settings.gcs_credentials.startswith("/"):
                # File path to credentials
                if os.path.exists(settings.gcs_credentials):
                    logger.info(f"Using service account file: {settings.gcs_credentials}")
                    self.client = storage.Client.from_service_account_json(
                        settings.gcs_credentials
                    )
                else:
                    raise FileNotFoundError(
                        f"Credentials file not found: {settings.gcs_credentials}"
                    )
            else:
                # JSON string credentials
                import json
                creds_info = json.loads(settings.gcs_credentials)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_info
                )
                self.client = storage.Client(
                    credentials=credentials,
                    project=settings.gcs_project_id
                )
        else:
            # Use Application Default Credentials
            logger.info("Using Application Default Credentials")
            self.client = storage.Client(project=settings.gcs_project_id or None)

        logger.info("GCS client initialized successfully")

    def _ensure_bucket_exists(self):
        """Ensure the bucket exists, creating it if necessary."""
        self.bucket = self.client.bucket(self.bucket_name)

        try:
            if self.bucket.exists():
                logger.info(f"Bucket {self.bucket_name} found")
                return
        except Exception:
            pass

        # Try to create bucket
        try:
            logger.info(f"Creating bucket {self.bucket_name} in {settings.gcs_location}")
            self.bucket.create(location=settings.gcs_location)
            logger.info(f"Bucket {self.bucket_name} created successfully")
        except Exception as e:
            logger.warning(f"Failed to create bucket with location: {e}")
            # Retry without location
            try:
                self.bucket.create()
                logger.info(f"Bucket {self.bucket_name} created (default location)")
            except Exception as e2:
                logger.error(f"Failed to create bucket: {e2}")
                raise

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
        Upload file content to GCS.

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

        # Build full path with tenant prefix
        prefix = self.get_tenant_prefix(tenant_id, user_id)
        full_path = f"{prefix}{object_name}"

        blob = self.bucket.blob(full_path)

        if metadata:
            blob.metadata = metadata

        if content_type:
            blob.content_type = content_type

        # Use temp file for upload (memory efficient)
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            try:
                temp_file.write(content)
                temp_file.flush()
                blob.upload_from_filename(temp_file.name)
            finally:
                os.unlink(temp_file.name)

        logger.info(f"File uploaded: {full_path} ({len(content)} bytes)")

        return {
            "object_name": full_path,
            "size": len(content),
            "bucket": self.bucket_name,
            "content_type": content_type,
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
        Download file content from GCS.

        Args:
            object_name: Object name to download
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            File content as bytes or None if not found
        """
        if not self._initialized:
            self.initialize()

        # Build full path if not already prefixed
        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            full_path = f"{prefix}{object_name}"
        else:
            full_path = object_name

        blob = self.bucket.blob(full_path)

        if not blob.exists():
            logger.warning(f"File not found: {full_path}")
            return None

        content = blob.download_as_bytes()
        logger.info(f"File downloaded: {full_path}")
        return content

    def delete_file(
        self,
        object_name: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Delete a file from GCS.

        Args:
            object_name: Object name to delete
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            True if deleted successfully
        """
        if not self._initialized:
            self.initialize()

        # Build full path
        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            full_path = f"{prefix}{object_name}"
        else:
            full_path = object_name

        blob = self.bucket.blob(full_path)

        if not blob.exists():
            logger.warning(f"File not found for deletion: {full_path}")
            return False

        blob.delete()
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

        # Build search prefix
        tenant_prefix = self.get_tenant_prefix(tenant_id, user_id)
        full_prefix = f"{tenant_prefix}{prefix}"

        blobs = self.bucket.list_blobs(prefix=full_prefix, max_results=limit)

        files = []
        for blob in blobs:
            # Remove tenant prefix from name for cleaner response
            relative_name = blob.name.replace(tenant_prefix, "", 1)

            files.append({
                "name": relative_name,
                "full_path": blob.name,
                "size": blob.size,
                "content_type": blob.content_type,
                "created": blob.time_created.isoformat() if blob.time_created else None,
                "updated": blob.updated.isoformat() if blob.updated else None,
                "metadata": blob.metadata or {},
            })

        logger.info(f"Listed {len(files)} files for tenant {tenant_id}")
        return files

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

        # Build full path
        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            full_path = f"{prefix}{object_name}"
        else:
            full_path = object_name

        blob = self.bucket.blob(full_path)

        if not blob.exists():
            return None

        blob.reload()

        return {
            "name": object_name,
            "full_path": full_path,
            "size": blob.size,
            "content_type": blob.content_type,
            "created": blob.time_created.isoformat() if blob.time_created else None,
            "updated": blob.updated.isoformat() if blob.updated else None,
            "metadata": blob.metadata or {},
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

        # Build full path
        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            full_path = f"{prefix}{object_name}"
        else:
            full_path = object_name

        expiration = expiration_seconds or settings.signed_url_expiration
        expires_at = datetime.utcnow() + timedelta(seconds=expiration)

        blob = self.bucket.blob(full_path)

        url_params = {
            "version": "v4",
            "expiration": timedelta(seconds=expiration),
            "method": method,
        }

        if content_type and method.upper() == "PUT":
            url_params["content_type"] = content_type

        url = blob.generate_signed_url(**url_params)

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
        Move/rename a file within the bucket.

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

        prefix = self.get_tenant_prefix(tenant_id, user_id)

        # Build full paths
        if not source_name.startswith(f"tenant-{tenant_id}"):
            source_path = f"{prefix}{source_name}"
        else:
            source_path = source_name

        if not destination_name.startswith(f"tenant-{tenant_id}"):
            dest_path = f"{prefix}{destination_name}"
        else:
            dest_path = destination_name

        source_blob = self.bucket.blob(source_path)

        if not source_blob.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Copy to destination
        self.bucket.copy_blob(source_blob, self.bucket, dest_path)

        # Delete source
        source_blob.delete()

        logger.info(f"File moved: {source_path} -> {dest_path}")

        return {
            "source": source_name,
            "destination": destination_name,
            "bucket": self.bucket_name,
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

        if not object_name.startswith(f"tenant-{tenant_id}"):
            prefix = self.get_tenant_prefix(tenant_id, user_id)
            full_path = f"{prefix}{object_name}"
        else:
            full_path = object_name

        blob = self.bucket.blob(full_path)
        return blob.exists()


# Global service instance
_gcs_service: Optional[GCSService] = None


def get_gcs_service(bucket_name: Optional[str] = None) -> GCSService:
    """
    Get or create the GCS service singleton.

    Args:
        bucket_name: Optional bucket name

    Returns:
        GCSService instance
    """
    global _gcs_service

    if _gcs_service is None:
        _gcs_service = GCSService(bucket_name)
        _gcs_service.initialize()

    return _gcs_service
