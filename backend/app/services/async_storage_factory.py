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
    async def create_storage_service(user_id: Optional[str] = None, db: Optional[AsyncSession] = None):
        """
        Creates the appropriate storage service instance asynchronously.

        Priority:
        1. StorageService (microservice) - primary
        2. MockStorageService - only for testing

        Args:
            user_id: User ID (optional)
            db: Async database session (optional, retained for API compatibility)

        Returns:
            Storage service instance
        """
        # db is retained in the signature for backwards compatibility with
        # legacy callers; it is no longer used to look up a tenant row (the
        # Tenant model was removed when single-tenant mode was adopted).
        del db  # explicitly unused

        # In testing mode, check if we want to use mock
        if os.getenv("TESTING") == "true" and os.getenv("USE_MOCK_STORAGE") == "true":
            logger.info("Using MockStorageService for testing")
            from app.services.storage_factory import MockStorageService
            return MockStorageService(user_id)

        # Check if in testing mode but credentials are not available
        testing_mode = os.getenv("TESTING") == "true"
        credentials_available = (
            os.getenv("GCS_CREDENTIALS") and
            os.path.exists(os.getenv("GCS_CREDENTIALS", ""))
        ) or os.getenv("GCS_PROJECT_ID")

        # Use async storage service (microservice)
        try:
            from app.services.async_storage_service import AsyncStorageService

            # Quick connectivity test
            if not testing_mode or credentials_available:
                storage = AsyncStorageService(user_id=user_id)
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
            return MockStorageService(user_id)
        
        # In production, fail if no credentials
        error_msg = f"No storage service available and not in testing mode. "
        error_msg += f"Storage service URL: {settings.STORAGE_SERVICE_URL}, "
        error_msg += f"GCS credentials available: {credentials_available}, "
        error_msg += f"Is Cloud Run: {settings.IS_CLOUD_RUN}"
        raise Exception(error_msg)