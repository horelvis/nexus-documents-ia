"""
Security module for Langroid Service
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, Header, Depends
from functools import wraps
import httpx
import jwt
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)


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
            # In production, this would call the main backend's auth service
            # For now, we'll implement basic validation
            
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
            # Check if agent exists and user has access
            # This would typically check the agent's tenant and visibility settings
            
            # For admin/superuser operations (create, delete, modify)
            if operation in ["create", "delete", "modify"]:
                await self.verify_tenant_access(tenant_id, user_id, "admin")
            
            # For regular operations, check agent permissions
            # This is simplified - in production you'd check agent ownership/visibility
            
            return True
            
        except Exception as e:
            logger.error(f"Error verifying agent access: {str(e)}")
            return False
    
    async def _get_user_info(self, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get user information from backend"""
        
        try:
            # This would make an actual HTTP request to the backend
            # For now, return mock data
            
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


# FastAPI dependencies
async def get_api_key(api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Extract and validate API key from headers"""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    
    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key


async def get_tenant_id(tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Extract tenant ID from headers"""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID required")
    return tenant_id


async def get_user_id(user_id: str = Header(..., alias="X-User-ID")) -> str:
    """Extract user ID from headers"""
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    return user_id


async def verify_admin_access(
    api_key: str = Depends(get_api_key),
    tenant_id: str = Depends(get_tenant_id),
    user_id: str = Depends(get_user_id)
) -> Dict[str, Any]:
    """Verify admin access for agent management operations"""
    
    return await security_service.verify_tenant_access(
        tenant_id, user_id, "admin"
    )


async def verify_user_access(
    api_key: str = Depends(get_api_key),
    tenant_id: str = Depends(get_tenant_id),
    user_id: str = Depends(get_user_id)
) -> Dict[str, Any]:
    """Verify basic user access"""
    
    return await security_service.verify_tenant_access(
        tenant_id, user_id, "user"
    )


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