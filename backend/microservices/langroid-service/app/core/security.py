"""
Security module for Langroid Service
Unified implementation following common pattern
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, Depends, Request
from functools import wraps
import httpx

from app.core.config import settings

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


def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool:
    """Validate API key"""
    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def validate_service_access(
    tenant_id: Optional[str] = Depends(get_tenant_id_from_header),
    user_id: Optional[str] = Depends(get_user_id_from_header),
    api_key_valid: bool = Depends(validate_api_key)
) -> dict:
    """Validate service access and return context"""
    
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "authenticated": True,
        "api_key_valid": api_key_valid
    }


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


class SecurityService:
    """Security service for authentication and authorization"""
    
    def __init__(self):
        self.backend_url = "http://backend:8000"
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def verify_tenant_access(
        self,
        tenant_id: str,
        user_id: str,
        required_role: str = "user"
    ) -> Dict[str, Any]:
        """Verify user has access to tenant and required role"""
        
        try:
            if not tenant_id or not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Missing tenant_id or user_id"
                )
            
            # Mock user verification (replace with actual backend call)
            user_info = await self._get_user_info(user_id, tenant_id)
            
            if not user_info:
                raise HTTPException(
                    status_code=404,
                    detail="User not found or no access to tenant"
                )
            
            # Check role requirements for agent management
            if required_role in ["admin", "superuser"]:
                user_role = user_info.get("role", "user")
                if user_role not in ["admin", "superuser"]:
                    raise HTTPException(
                        status_code=403,
                        detail="Admin or superuser role required for this operation"
                    )
            
            return user_info
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error verifying tenant access: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Error verifying access"
            )
    
    async def verify_agent_access(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        operation: str = "read"
    ) -> bool:
        """Verify user has access to specific agent"""
        
        try:
            # For admin/superuser operations (create, delete, modify)
            if operation in ["create", "delete", "modify"]:
                await self.verify_tenant_access(tenant_id, user_id, "admin")
            
            return True
            
        except Exception as e:
            logger.error(f"Error verifying agent access: {str(e)}")
            return False
    
    async def _get_user_info(self, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get user information from backend"""
        
        try:
            # Mock response based on user_id patterns
            if user_id.endswith("_admin"):
                return {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "role": "admin",
                    "permissions": ["read", "write", "admin"]
                }
            elif user_id.endswith("_super"):
                return {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "role": "superuser",
                    "permissions": ["read", "write", "admin", "superuser"]
                }
            else:
                return {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "role": "user",
                    "permissions": ["read"]
                }
                
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}")
            return None


# Global security service instance
security_service = SecurityService()


# Legacy functions for backwards compatibility
async def verify_admin_access(context: dict = Depends(validate_service_access)) -> Dict[str, Any]:
    """Verify admin access for agent management operations"""
    tenant_id = context.get("tenant_id")
    user_id = context.get("user_id")
    
    if not tenant_id or not user_id:
        raise HTTPException(status_code=400, detail="Tenant ID and User ID required in headers")
    
    return await security_service.verify_tenant_access(tenant_id, user_id, "admin")


async def verify_user_access(context: dict = Depends(validate_service_access)) -> Dict[str, Any]:
    """Verify basic user access"""
    tenant_id = context.get("tenant_id")
    user_id = context.get("user_id")
    
    if not tenant_id or not user_id:
        raise HTTPException(status_code=400, detail="Tenant ID and User ID required in headers")
    
    return await security_service.verify_tenant_access(tenant_id, user_id, "user")


def require_admin(func):
    """Decorator to require admin access"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract tenant_id and user_id from kwargs
        tenant_id = kwargs.get("tenant_id")
        user_id = kwargs.get("user_id")
        
        if not tenant_id or not user_id:
            raise HTTPException(
                status_code=400,
                detail="Tenant ID and User ID required"
            )
        
        # Verify admin access
        await security_service.verify_tenant_access(tenant_id, user_id, "admin")
        
        return await func(*args, **kwargs)
    
    return wrapper


def require_agent_access(operation: str = "read"):
    """Decorator to require agent access"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            agent_id = kwargs.get("agent_id")
            tenant_id = kwargs.get("tenant_id")
            user_id = kwargs.get("user_id")
            
            if not all([agent_id, tenant_id, user_id]):
                raise HTTPException(
                    status_code=400,
                    detail="Agent ID, Tenant ID and User ID required"
                )
            
            # Verify agent access
            has_access = await security_service.verify_agent_access(
                agent_id, tenant_id, user_id, operation
            )
            
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied to agent"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator