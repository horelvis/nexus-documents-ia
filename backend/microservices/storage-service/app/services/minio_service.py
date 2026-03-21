"""
MinIO storage service — S3-compatible object storage.

Uses the official minio Python SDK for synchronous operations
wrapped in asyncio.to_thread() for non-blocking calls.
"""

import asyncio
import io
import logging
from typing import Any, Dict, Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinIOStorageService:
    """MinIO S3-compatible storage client."""

    def __init__(self):
        self._client: Optional[Minio] = None
        self._bucket = settings.minio_bucket

    async def initialize(self) -> None:
        """Initialize MinIO client and ensure bucket exists."""
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )

        def _ensure_bucket():
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"Created MinIO bucket: {self._bucket}")

        await asyncio.to_thread(_ensure_bucket)
        logger.info(f"MinIO storage initialized: {settings.minio_endpoint}/{self._bucket}")

    async def upload(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> Dict[str, Any]:
        """Upload bytes to MinIO."""
        def _upload():
            self._client.put_object(
                self._bucket, object_name,
                io.BytesIO(data), len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_upload)
        logger.info(f"Uploaded: {object_name} ({len(data)} bytes)")
        return {"object_name": object_name, "size": len(data), "bucket": self._bucket}

    async def download(self, object_name: str) -> Optional[bytes]:
        """Download bytes from MinIO."""
        def _download():
            try:
                response = self._client.get_object(self._bucket, object_name)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except S3Error as e:
                if e.code == "NoSuchKey":
                    return None
                raise

        return await asyncio.to_thread(_download)

    async def delete(self, object_name: str) -> bool:
        """Delete object from MinIO."""
        def _delete():
            try:
                self._client.remove_object(self._bucket, object_name)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_delete)

    async def exists(self, object_name: str) -> bool:
        """Check if object exists in MinIO."""
        def _exists():
            try:
                self._client.stat_object(self._bucket, object_name)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_exists)


# Singleton
minio_storage = MinIOStorageService()
