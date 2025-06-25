import logging
from typing import Optional, Tuple, BinaryIO, Union, Dict, Any, List
from datetime import datetime
from fastapi import UploadFile

from app.services.async_storage_client import AsyncStorageClient

logger = logging.getLogger(__name__)

class AsyncStorageService:
    """
    Async StorageService that uses the storage microservice.
    Provides interface for document management via microservice.
    """
    
    def __init__(self, tenant_id: str, user_id: Optional[str] = None, bucket_name: Optional[str] = None):
        """
        Initialize the async storage service using the microservice.
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID (optional)
            bucket_name: Bucket name (optional)
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.bucket_name = bucket_name or f"storage-service-{tenant_id}"
        self.client = AsyncStorageClient(tenant_id, user_id, self.bucket_name)
    
    async def upload_file(
        self, 
        file: Union[UploadFile, BinaryIO, bytes], 
        object_name: str, 
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Upload a file to storage asynchronously.
        
        Args:
            file: File object to upload
            object_name: Object name in storage
            metadata: Associated file metadata
            
        Returns:
            True if uploaded successfully, False otherwise
        """
        try:
            # Extract filename from object_name
            filename = object_name.split("/")[-1]
            
            result = await self.client.upload_file(
                file=file,
                filename=filename,
                metadata=metadata
            )
            
            logger.info(f"File uploaded successfully: {object_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload file {object_name}: {e}")
            return False
    
    async def download_file(self, object_name: str) -> Optional[bytes]:
        """
        Download a file from storage asynchronously.
        
        Args:
            object_name: Object name to download (can include full or relative path)
            
        Returns:
            File content as bytes or None if not found
        """
        try:
            # If object_name includes tenant prefix, remove it
            # Expected format: tenant-{id}/user-{id}/filename or tenant-{id}/system/filename
            file_path = object_name
            
            # Remove tenant prefix if present
            if object_name.startswith(f"tenant-{self.tenant_id}/"):
                # Remove "tenant-{id}/" from beginning
                path_without_tenant = object_name[len(f"tenant-{self.tenant_id}/"):]
                
                # If includes user prefix, remove it too
                if self.user_id and path_without_tenant.startswith(f"user-{self.user_id}/"):
                    file_path = path_without_tenant[len(f"user-{self.user_id}/"):]
                elif path_without_tenant.startswith("system/"):
                    file_path = path_without_tenant[len("system/"):]
                else:
                    file_path = path_without_tenant
            
            content = await self.client.download_file(file_path)
            
            # Fallback: if not found with full path, try filename only
            if not content and "/" in file_path:
                filename_only = file_path.split("/")[-1]
                logger.info(f"Trying fallback with filename only: {filename_only}")
                content = await self.client.download_file(filename_only)
                if content:
                    logger.info(f"File downloaded successfully with fallback: {object_name} -> {filename_only}")
                    return content
            
            if content:
                logger.info(f"File downloaded successfully: {object_name} -> {file_path}")
            else:
                logger.warning(f"File not found: {object_name} -> {file_path}")
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to download file {object_name}: {e}")
            return None
    
    async def delete_file(self, object_name: str) -> bool:
        """
        Delete a file from storage asynchronously.
        
        Args:
            object_name: Object name to delete (can include full or relative path)
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # If object_name includes tenant prefix, remove it
            file_path = object_name
            
            # Remove tenant prefix if present
            if object_name.startswith(f"tenant-{self.tenant_id}/"):
                # Remove "tenant-{id}/" from beginning
                path_without_tenant = object_name[len(f"tenant-{self.tenant_id}/"):]
                
                # If includes user prefix, remove it too
                if self.user_id and path_without_tenant.startswith(f"user-{self.user_id}/"):
                    file_path = path_without_tenant[len(f"user-{self.user_id}/"):]
                elif path_without_tenant.startswith("system/"):
                    file_path = path_without_tenant[len("system/"):]
                else:
                    file_path = path_without_tenant
            
            success = await self.client.delete_file(file_path)
            
            # Fallback: if not found with full path, try filename only
            if not success and "/" in file_path:
                filename_only = file_path.split("/")[-1]
                logger.info(f"Trying delete fallback with filename only: {filename_only}")
                success = await self.client.delete_file(filename_only)
                if success:
                    logger.info(f"File deleted successfully with fallback: {object_name} -> {filename_only}")
                    return success
            
            if success:
                logger.info(f"File deleted successfully: {object_name} -> {file_path}")
            else:
                logger.warning(f"File not found for deletion: {object_name} -> {file_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete file {object_name}: {e}")
            return False
    
    async def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """
        List files in storage asynchronously.
        
        Args:
            prefix: Prefix to filter files
            
        Returns:
            List of file information
        """
        try:
            files = await self.client.list_files(prefix=prefix)
            
            # Convert format for compatibility with existing code
            result = []
            for file_info in files:
                result.append({
                    "name": file_info.get("name", ""),
                    "size": file_info.get("size", 0),
                    "updated": file_info.get("updated"),
                    "content_type": file_info.get("content_type"),
                    "metadata": file_info.get("metadata", {})
                })
            
            logger.info(f"Listed {len(result)} files with prefix '{prefix}'")
            return result
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            return []
    
    async def generate_upload_signed_url(
        self, 
        object_name: str, 
        content_type: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for uploading an object asynchronously.
        
        Args:
            object_name: Object name to upload
            content_type: MIME content type
            expiration: Expiration time in seconds
            
        Returns:
            Tuple with signed URL and expiration date
        """
        try:
            # Extract filename from object_name
            filename = object_name.split("/")[-1]
            
            url, expires_at = await self.client.generate_upload_signed_url(
                filename=filename,
                content_type=content_type,
                expiration=expiration
            )
            
            logger.info(f"Generated upload signed URL for: {object_name}")
            return url, expires_at
            
        except Exception as e:
            logger.error(f"Failed to generate upload signed URL for {object_name}: {e}")
            raise
    
    async def generate_download_signed_url(
        self, 
        object_name: str,
        expiration: Optional[int] = None
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for downloading an object asynchronously.
        
        Args:
            object_name: Object name to download (can include full or relative path)
            expiration: Expiration time in seconds
            
        Returns:
            Tuple with signed URL and expiration date
        """
        try:
            # If object_name includes tenant prefix, remove it
            file_path = object_name
            
            # Remove tenant prefix if present
            if object_name.startswith(f"tenant-{self.tenant_id}/"):
                # Remove "tenant-{id}/" from beginning
                path_without_tenant = object_name[len(f"tenant-{self.tenant_id}/"):]
                
                # If includes user prefix, remove it too
                if self.user_id and path_without_tenant.startswith(f"user-{self.user_id}/"):
                    file_path = path_without_tenant[len(f"user-{self.user_id}/"):]
                elif path_without_tenant.startswith("system/"):
                    file_path = path_without_tenant[len("system/"):]
                else:
                    file_path = path_without_tenant
            
            try:
                url, expires_at = await self.client.generate_download_signed_url(
                    file_path=file_path,
                    expiration=expiration
                )
                logger.info(f"Generated download signed URL for: {object_name} -> {file_path}")
                return url, expires_at
            except Exception as e:
                # Fallback: if fails with full path, try filename only
                if "/" in file_path:
                    filename_only = file_path.split("/")[-1]
                    logger.info(f"Trying signed URL fallback with filename only: {filename_only}")
                    url, expires_at = await self.client.generate_download_signed_url(
                        file_path=filename_only,
                        expiration=expiration
                    )
                    logger.info(f"Generated download signed URL with fallback: {object_name} -> {filename_only}")
                    return url, expires_at
                else:
                    raise
            
        except Exception as e:
            logger.error(f"Failed to generate download signed URL for {object_name}: {e}")
            raise
    
    async def cleanup_test_bucket(self) -> bool:
        """
        Clean test bucket completely by removing all files asynchronously.
        Only works in testing mode.
        
        Returns:
            True if cleaned successfully, False otherwise
        """
        try:
            result = await self.client.cleanup_test_bucket()
            
            logger.info(f"Test bucket cleaned: {result}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup test bucket: {e}")
            return False
    
    async def delete_test_bucket(self) -> bool:
        """
        Delete test bucket completely asynchronously.
        Alias for cleanup_test_bucket for compatibility.
        
        Returns:
            True if deleted successfully, False otherwise
        """
        return await self.cleanup_test_bucket()
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check storage service health asynchronously.
        
        Returns:
            Service status
        """
        try:
            return await self.client.health_check()
        except Exception as e:
            logger.error(f"Storage service health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }