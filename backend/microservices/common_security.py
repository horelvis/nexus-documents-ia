"""
Common Security Module for Microservices
Unified implementation to avoid conflicts between path params and headers
"""
import logging
from fastapi import HTTPException, Depends, Request
from typing import Optional

logger = logging.getLogger(__name__)


def get_api_key_from_header(request: Request) -> str:
    """Extract API key from X-API-Key header"""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    return api_key


def get_tenant_id_from_header(request: Request) -> Optional[str]:
    """Extract tenant ID from X-Tenant-ID header (optional for routes with path param)"""
    return request.headers.get("X-Tenant-ID")


def get_user_id_from_header(request: Request) -> Optional[str]:
    """Extract user ID from X-User-ID header (optional)"""
    return request.headers.get("X-User-ID")


def get_bucket_name_from_header(request: Request) -> Optional[str]:
    """Extract bucket name from X-Bucket-Name header (optional)"""
    return request.headers.get("X-Bucket-Name")


def validate_api_key(api_key: str, expected_api_key: str) -> bool:
    """Validate API key against expected value"""
    if api_key != expected_api_key:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def create_security_dependency(expected_api_key: str):
    """Factory function to create security dependency with specific API key"""
    
    def validate_api_key_wrapper(api_key: str = Depends(get_api_key_from_header)) -> bool:
        """Validate API key wrapper"""
        return validate_api_key(api_key, expected_api_key)
    
    def validate_service_access(
        tenant_id: Optional[str] = Depends(get_tenant_id_from_header),
        user_id: Optional[str] = Depends(get_user_id_from_header),
        bucket_name: Optional[str] = Depends(get_bucket_name_from_header),
        api_key_valid: bool = Depends(validate_api_key_wrapper)
    ) -> dict:
        """Validate service access and return context"""
        
        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "bucket_name": bucket_name,
            "authenticated": True,
            "api_key_valid": api_key_valid
        }
    
    return validate_service_access


def create_tenant_validator():
    """Create tenant validation helper"""
    
    def validate_tenant_access(tenant_id: str, context: dict) -> str:
        """Validate tenant access and return validated tenant_id"""
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Tenant ID required")
        
        # If tenant_id is also in headers, validate they match
        header_tenant_id = context.get("tenant_id")
        if header_tenant_id and header_tenant_id != tenant_id:
            raise HTTPException(
                status_code=403, 
                detail="Tenant ID mismatch between path and header"
            )
        
        return tenant_id
    
    return validate_tenant_access


# Utility functions for bucket and path generation
def get_bucket_name(base_bucket_name: str, tenant_id: str, testing: bool = False) -> str:
    """Generate bucket name based on tenant (one bucket per tenant for GDPR)"""
    base_name = f"{base_bucket_name}-{tenant_id}"
    if testing:
        return f"{base_name}-test"
    return base_name


def get_object_path(tenant_id: str, user_id: Optional[str], filename: str) -> str:
    """Generate object path with tenant/user isolation"""
    if user_id:
        return f"tenant-{tenant_id}/user-{user_id}/{filename}"
    else:
        return f"tenant-{tenant_id}/system/{filename}"


def validate_file_extension(filename: str, allowed_extensions: list) -> bool:
    """Validate file extension against allowed list"""
    if "." not in filename:
        return False
    
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in allowed_extensions


def validate_file_size(content_length: Optional[int], max_size: int) -> bool:
    """Validate file size against maximum"""
    if content_length is None:
        return True  # If size can't be determined, allow it
    
    return content_length <= max_size