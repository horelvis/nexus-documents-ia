import logging
import os
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings

logger = logging.getLogger(__name__)

class AsyncStorageServiceFactory:
    """Async version of StorageServiceFactory for use with async sessions"""
    
    @staticmethod
    async def create_storage_service(tenant_id: str, user_id: Optional[str] = None, db: Optional[AsyncSession] = None):
        """
        Creates the appropriate storage service instance asynchronously.
        
        Priority:
        1. StorageService (microservice) - primary
        2. MockStorageService - only for testing
        
        Args:
            tenant_id: Tenant ID
            user_id: User ID (optional)
            db: Async database session (optional)
            
        Returns:
            Storage service instance
        """
        
        # In testing mode, check if we want to use mock
        if os.getenv("TESTING") == "true" and os.getenv("USE_MOCK_STORAGE") == "true":
            logger.info("Using MockStorageService for testing")
            from app.services.storage_factory import MockStorageService
            return MockStorageService(tenant_id, user_id)
        
        # Check if in testing mode but credentials are not available
        testing_mode = os.getenv("TESTING") == "true"
        credentials_available = (
            os.getenv("GCS_CREDENTIALS") and 
            os.path.exists(os.getenv("GCS_CREDENTIALS", ""))
        ) or os.getenv("GCS_PROJECT_ID")
        
        # Get bucket_name from tenant if there's a DB session
        bucket_name = None
        if db:
            from app.db.models import Tenant
            # Use async query
            result = await db.execute(
                select(Tenant).filter(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()
            if tenant and tenant.bucket_name:
                bucket_name = tenant.bucket_name
        
        # Use async storage service (microservice)
        try:
            from app.services.async_storage_service import AsyncStorageService
            
            # Quick connectivity test
            if not testing_mode or credentials_available:
                storage = AsyncStorageService(tenant_id, user_id, bucket_name)
                health = await storage.health_check()
                
                if health.get("status") == "healthy":
                    logger.info("Using AsyncStorageService (microservice)")
                    return storage
                else:
                    logger.warning("Storage microservice unhealthy")
            else:
                logger.info("Testing mode without credentials, skipping microservice")
                
        except Exception as e:
            logger.warning(f"Storage microservice unavailable: {e}")
        
        # If we're in testing, use mock as last resort
        if testing_mode:
            logger.warning("Using MockStorageService as last resort for testing")
            from app.services.storage_factory import MockStorageService
            return MockStorageService(tenant_id, user_id)
        
        # In production, fail if no credentials
        raise Exception("No storage service available and not in testing mode")