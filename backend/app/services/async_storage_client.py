import httpx
import logging
import io
import mimetypes
import time
import asyncio
from typing import Optional, Tuple, BinaryIO, Union, Dict, Any, List
from datetime import datetime
from fastapi import UploadFile, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

class AsyncStorageClient:
    """Async client for communicating with the storage microservice"""
    
    def __init__(self, tenant_id: str, user_id: Optional[str] = None, bucket_name: Optional[str] = None):
        """
        Initialize the async storage client.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID (optional)
            bucket_name: Bucket name (optional, will be obtained from tenant if not provided)
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        # Try internal URL first, then fallback to external URL
        self.base_url = getattr(settings, 'STORAGE_SERVICE_INTERNAL_URL', 
                               getattr(settings, 'STORAGE_SERVICE_URL', 'http://storage-service:8001'))
        self.api_key = settings.STORAGE_API_KEY
        
        # Common headers for all requests
        self.headers = {
            "X-API-Key": self.api_key,
            "X-Tenant-ID": self.tenant_id,
        }
        
        if self.user_id:
            self.headers["X-User-ID"] = self.user_id
            
        # Add bucket name if provided
        if bucket_name:
            self.headers["X-Bucket-Name"] = bucket_name
    
    def _get_mimetype(self, filename: str, fallback: str = "application/octet-stream") -> str:
        """
        Detect mimetype based on file extension.
        
        Args:
            filename: File name
            fallback: Default mimetype if detection fails
            
        Returns:
            Detected mimetype or fallback
        """
        # Manual mapping for common document types
        common_mimetypes = {
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
        
        # Get extension in lowercase
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Search in manual mapping first
        if ext in common_mimetypes:
            return common_mimetypes[ext]
        
        # Fallback to standard mimetypes
        mimetype, _ = mimetypes.guess_type(filename)
        return mimetype or fallback
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> httpx.Response:
        """
        Make an async HTTP request to the storage service.
        
        Args:
            method: HTTP method
            endpoint: Endpoint (without base URL)
            **kwargs: Additional arguments for httpx
            
        Returns:
            httpx Response
        """
        url = f"{self.base_url}/api/v1/storage{endpoint}"
        
        # Merge headers
        request_headers = {**self.headers}
        if "headers" in kwargs:
            request_headers.update(kwargs["headers"])
            kwargs["headers"] = request_headers
        else:
            kwargs["headers"] = request_headers
        
        # Implement retry with exponential backoff for rate limits
        max_retries = 3
        base_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(method, url, **kwargs)
                    response.raise_for_status()
                    return response
                    
            except httpx.HTTPStatusError as e:
                # If rate limit (429), retry with backoff
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Rate limit hit, retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                    
                logger.error(f"Storage service HTTP error: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Storage service error: {e.response.text}"
                )
            except (httpx.RequestError, httpx.TimeoutException, httpx.ConnectError) as e:
                logger.error(f"Storage service connection error: {e}")
                raise HTTPException(
                    status_code=503,
                    detail="Storage service unavailable"
                )
    
    async def upload_file(
        self, 
        file: Union[UploadFile, BinaryIO, bytes], 
        filename: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Upload a file to storage asynchronously.
        
        Args:
            file: File to upload
            filename: File name
            metadata: Optional metadata
            
        Returns:
            Uploaded file information
        """
        try:
            # Detect mimetype
            detected_mimetype = self._get_mimetype(filename)
            
            # Prepare file for upload
            if isinstance(file, bytes):
                files = {"file": (filename, io.BytesIO(file), detected_mimetype)}
            elif isinstance(file, UploadFile):
                content = await file.read()
                await file.seek(0)  # Reset for later use
                # Use UploadFile mimetype if available, otherwise detected
                mimetype = file.content_type or detected_mimetype
                files = {"file": (filename, io.BytesIO(content), mimetype)}
            else:
                # For BinaryIO
                file.seek(0)
                content = file.read()
                file.seek(0)  # Reset
                files = {"file": (filename, io.BytesIO(content), detected_mimetype)}
            
            # Prepare form data
            data = {}
            if metadata:
                import json
                data["metadata"] = json.dumps(metadata)
            
            response = await self._make_request(
                "POST", 
                "/upload", 
                files=files,
                data=data
            )
            
            result = response.json()
            logger.info(f"File uploaded successfully: {filename}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload file {filename}: {e}")
            raise
    
    async def download_file(self, file_path: str) -> Optional[bytes]:
        """
        Download a file from storage asynchronously.
        
        Args:
            file_path: File path
            
        Returns:
            File content as bytes or None if not found
        """
        try:
            response = await self._make_request("GET", f"/download/{file_path}")
            
            logger.info(f"File downloaded successfully: {file_path}")
            return response.content
            
        except HTTPException as e:
            if e.status_code == 404:
                logger.warning(f"File not found: {file_path}")
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to download file {file_path}: {e}")
            raise
    
    async def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from storage asynchronously.
        
        Args:
            file_path: File path
            
        Returns:
            True if deleted successfully
        """
        try:
            response = await self._make_request("DELETE", f"/delete/{file_path}")
            
            logger.info(f"File deleted successfully: {file_path}")
            return True
            
        except HTTPException as e:
            if e.status_code == 404:
                logger.warning(f"File not found for deletion: {file_path}")
                return False
            raise
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            raise
    
    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get file information asynchronously.
        
        Args:
            file_path: File path
            
        Returns:
            File information or None if not found
        """
        try:
            response = await self._make_request("GET", f"/info/{file_path}")
            
            result = response.json()
            logger.info(f"File info retrieved: {file_path}")
            return result
            
        except HTTPException as e:
            if e.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get file info {file_path}: {e}")
            raise
    
    async def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """
        List tenant files asynchronously.
        
        Args:
            prefix: Prefix to filter files
            limit: File limit
            
        Returns:
            List of file information
        """
        try:
            params = {"prefix": prefix, "limit": limit}
            response = await self._make_request("GET", "/list", params=params)
            
            result = response.json()
            files = result.get("files", [])
            
            logger.info(f"Listed {len(files)} files with prefix '{prefix}'")
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            raise
    
    async def generate_upload_signed_url(
        self, 
        filename: str, 
        content_type: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for file upload asynchronously.
        
        Args:
            filename: File name
            content_type: MIME content type
            expiration: Expiration time in seconds
            
        Returns:
            Tuple with signed URL and expiration date
        """
        try:
            payload = {
                "filename": filename,
                "content_type": content_type
            }
            
            if expiration:
                payload["expiration"] = expiration
            
            response = await self._make_request("POST", "/signed-url/upload", json=payload)
            
            result = response.json()
            url = result["url"]
            expires_at = datetime.fromisoformat(result["expires_at"])
            
            logger.info(f"Generated upload signed URL for: {filename}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate upload signed URL for {filename}: {e}")
            raise
    
    async def generate_download_signed_url(
        self, 
        file_path: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for file download asynchronously.
        
        Args:
            file_path: File path
            expiration: Expiration time in seconds
            
        Returns:
            Tuple with signed URL and expiration date
        """
        try:
            params = {}
            if expiration:
                params["expiration"] = expiration
            
            response = await self._make_request(
                "POST", 
                f"/signed-url/download/{file_path}",
                params=params
            )
            
            result = response.json()
            url = result["url"]
            expires_at = datetime.fromisoformat(result["expires_at"])
            
            logger.info(f"Generated download signed URL for: {file_path}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate download signed URL for {file_path}: {e}")
            raise
    
    async def cleanup_test_bucket(self) -> Dict[str, Any]:
        """
        Clean test bucket asynchronously. Only for testing.
        
        Returns:
            Cleanup information
        """
        try:
            response = await self._make_request("POST", "/cleanup")
            
            result = response.json()
            logger.info(f"Test bucket cleaned: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to cleanup test bucket: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check storage service health asynchronously.
        
        Returns:
            Service status
        """
        try:
            response = await self._make_request("GET", "/health")
            return response.json()
        except Exception as e:
            logger.error(f"Storage service health check failed: {e}")
            raise
