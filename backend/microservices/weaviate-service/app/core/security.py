"""Security utilities for Weaviate service"""
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """Verify the API key for microservice communication"""
    if not credentials:
        logger.warning("⚠️ No credentials provided")
        raise HTTPException(
            status_code=401,
            detail="Missing API key"
        )
    
    if credentials.credentials != settings.api_key:
        logger.warning(f"⚠️ Invalid API key provided: {credentials.credentials[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return True

def get_tenant_collection_name(tenant_id: str, collection_type: str = "documents") -> str:
    """Generate tenant-specific collection name for Weaviate"""
    return f"{settings.collection_prefix}{tenant_id}_{collection_type}".lower().replace("-", "_")