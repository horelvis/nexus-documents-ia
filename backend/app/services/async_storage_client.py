"""
Async Storage Client

Async HTTP client for the storage microservice (Google Cloud Storage).
Provides file upload, download, deletion, and signed URL operations.
"""
from __future__ import annotations

import io
import json
import logging
import mimetypes
from datetime import datetime
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union

from fastapi import UploadFile

from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError, UpstreamError
from app.core.config import settings

logger = logging.getLogger(__name__)


# Common MIME type mappings
COMMON_MIMETYPES: Dict[str, str] = {
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.txt': 'text/plain',
    '.csv': 'text/csv',
    '.json': 'application/json',
    '.xml': 'application/xml',
    '.html': 'text/html',
    '.md': 'text/markdown',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.mp4': 'video/mp4',
    '.avi': 'video/x-msvideo',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.zip': 'application/zip',
    '.rar': 'application/vnd.rar',
    '.7z': 'application/x-7z-compressed',
}


def get_mimetype(filename: str, fallback: str = "application/octet-stream") -> str:
    """
    Detect MIME type based on file extension.

    Args:
        filename: File name
        fallback: Default MIME type if detection fails

    Returns:
        Detected MIME type or fallback
    """
    ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''

    # Check manual mapping first
    if ext in COMMON_MIMETYPES:
        return COMMON_MIMETYPES[ext]

    # Fallback to standard mimetypes module
    mimetype, _ = mimetypes.guess_type(filename)
    return mimetype or fallback


class AsyncStorageClient(BaseHTTPClient):
    """
    Async HTTP client for the storage microservice.

    Provides operations for:
    - File upload/download/delete
    - File info and listing
    - Signed URL generation
    - Health checks

    Example:
        client = AsyncStorageClient(user_id="u1")
        result = await client.upload_file(file_bytes, "document.pdf")
        url, expires = await client.generate_download_signed_url(result["file_path"])
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        bucket_name: Optional[str] = None
    ) -> None:
        """
        Initialize the async storage client.

        Args:
            user_id: User ID (optional)
            bucket_name: Bucket name (optional; defaults to the configured bucket)
        """
        # Try internal URL first, then external URL
        storage_url = getattr(
            settings, 'STORAGE_SERVICE_INTERNAL_URL',
            getattr(settings, 'STORAGE_SERVICE_URL', 'http://storage-service:8001')
        )
        self.storage_url = storage_url.rstrip("/")

        self.user_id = user_id
        self.bucket_name = bucket_name

        # Use custom API key for storage if configured
        api_key = getattr(settings, 'STORAGE_API_KEY', None) or settings.MICROSERVICES_API_KEY

        super().__init__(
            service_name="storage",
            base_url=self.storage_url,
            timeout_type="upload",  # 60s read, 120s write for large files
            api_key=api_key,
        )

    def _build_headers(
        self,
        extra_headers: Optional[Dict[str, str]] = None,
        user_id: Optional[str] = None,
        user_roles: Optional[list[str]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Override to add bucket name header."""
        headers = super()._build_headers(extra_headers, user_id, user_roles, request_id)

        # Add bucket name if configured
        if self.bucket_name:
            headers["X-Bucket-Name"] = self.bucket_name

        return headers

    async def upload_file(
        self,
        file: Union[UploadFile, BinaryIO, bytes],
        filename: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload a file to storage.

        Args:
            file: File to upload (bytes, BinaryIO, or UploadFile)
            filename: File name
            metadata: Optional metadata dictionary

        Returns:
            Dict with file information (file_path, size, etc.)

        Raises:
            HTTPClientError: On upload failure
        """
        # Detect MIME type
        detected_mimetype = get_mimetype(filename)

        # Prepare file for upload
        if isinstance(file, bytes):
            files = {"file": (filename, io.BytesIO(file), detected_mimetype)}
        elif isinstance(file, UploadFile):
            content = await file.read()
            await file.seek(0)  # Reset for later use
            mimetype = file.content_type or detected_mimetype
            files = {"file": (filename, io.BytesIO(content), mimetype)}
        else:
            # BinaryIO
            file.seek(0)
            content = file.read()
            file.seek(0)  # Reset
            files = {"file": (filename, io.BytesIO(content), detected_mimetype)}

        # Prepare form data
        data = {}
        if metadata:
            data["metadata"] = json.dumps(metadata)

        response = await self.request(
            "POST",
            "/api/v1/storage/upload",
            user_id=self.user_id,
            files=files,
            data=data if data else None,
        )

        result = response.json()
        logger.info(f"File uploaded successfully: {filename}")
        return result

    async def download_file(self, file_path: str) -> Optional[bytes]:
        """
        Download a file from storage.

        Args:
            file_path: Path to the file in storage

        Returns:
            File content as bytes, or None if not found
        """
        try:
            response = await self.request(
                "GET",
                f"/api/v1/storage/download/{file_path}",
                user_id=self.user_id,
            )
            logger.info(f"File downloaded successfully: {file_path}")
            return response.content

        except UpstreamError as e:
            if e.status_code == 404:
                logger.warning(f"File not found: {file_path}")
                return None
            raise

    async def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            file_path: Path to the file in storage

        Returns:
            True if deleted successfully, False if not found
        """
        try:
            await self.request(
                "DELETE",
                f"/api/v1/storage/delete/{file_path}",
                user_id=self.user_id,
            )
            logger.info(f"File deleted successfully: {file_path}")
            return True

        except UpstreamError as e:
            if e.status_code == 404:
                logger.warning(f"File not found for deletion: {file_path}")
                return False
            raise

    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get file information.

        Args:
            file_path: Path to the file in storage

        Returns:
            File information dict, or None if not found
        """
        try:
            response = await self.request(
                "GET",
                f"/api/v1/storage/info/{file_path}",
                user_id=self.user_id,
            )
            result = response.json()
            logger.debug(f"File info retrieved: {file_path}")
            return result

        except UpstreamError as e:
            if e.status_code == 404:
                return None
            raise

    async def list_files(
        self,
        prefix: str = "",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List files for the tenant.

        Args:
            prefix: Prefix to filter files
            limit: Maximum number of files to return

        Returns:
            List of file information dicts
        """
        response = await self.request(
            "GET",
            "/api/v1/storage/list",
            user_id=self.user_id,
            params={"prefix": prefix, "limit": limit},
        )

        result = response.json()
        files = result.get("files", [])
        logger.debug(f"Listed {len(files)} files with prefix '{prefix}'")
        return files

    async def generate_upload_signed_url(
        self,
        filename: str,
        content_type: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for file upload.

        Args:
            filename: File name
            content_type: MIME content type
            expiration: Expiration time in seconds

        Returns:
            Tuple of (signed_url, expiration_datetime)
        """
        payload = {
            "filename": filename,
            "content_type": content_type
        }
        if expiration:
            payload["expiration"] = expiration

        response = await self.request(
            "POST",
            "/api/v1/storage/signed-url/upload",
            user_id=self.user_id,
            json=payload,
        )

        result = response.json()
        url = result["url"]
        expires_at = datetime.fromisoformat(result["expires_at"])

        logger.debug(f"Generated upload signed URL for: {filename}")
        return url, expires_at

    async def generate_download_signed_url(
        self,
        file_path: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for file download.

        Args:
            file_path: Path to the file
            expiration: Expiration time in seconds

        Returns:
            Tuple of (signed_url, expiration_datetime)
        """
        params = {}
        if expiration:
            params["expiration"] = expiration

        response = await self.request(
            "POST",
            f"/api/v1/storage/signed-url/download/{file_path}",
            user_id=self.user_id,
            params=params if params else None,
        )

        result = response.json()
        url = result["url"]
        expires_at = datetime.fromisoformat(result["expires_at"])

        logger.debug(f"Generated download signed URL for: {file_path}")
        return url, expires_at

    async def move_file(self, source_path: str, destination_path: str) -> Dict[str, Any]:
        """
        Move a file to a new location.

        Args:
            source_path: Current file path
            destination_path: New file path

        Returns:
            Move operation result
        """
        payload = {
            "source_path": source_path,
            "destination_path": destination_path
        }

        response = await self.request(
            "POST",
            "/api/v1/storage/move",
            user_id=self.user_id,
            json=payload,
        )

        result = response.json()
        logger.info(f"File moved successfully: {source_path} -> {destination_path}")
        return result

    async def cleanup_test_bucket(self) -> Dict[str, Any]:
        """
        Clean test bucket. Only for testing.

        Returns:
            Cleanup information
        """
        response = await self.request(
            "POST",
            "/api/v1/storage/cleanup",
            user_id=self.user_id,
        )

        result = response.json()
        logger.info(f"Test bucket cleaned: {result}")
        return result

    async def health_check(self) -> Dict[str, Any]:
        """
        Check storage service health.

        Returns:
            Service status dict
        """
        try:
            # Use /health endpoint (storage-service compatible)
            response = await self.request(
                "GET",
                "/health",
            )
            return response.json()
        except HTTPClientError as e:
            logger.error(f"Storage service health check failed: {e}")
            return {"status": "unhealthy", "service": self.service_name, "error": str(e)}
