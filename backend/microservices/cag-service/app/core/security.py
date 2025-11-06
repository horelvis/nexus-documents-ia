"""Security utilities for CAG Service"""
from typing import Optional, Dict, Any
from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer
from loguru import logger

from .config import settings

security = HTTPBearer()


async def verify_api_key(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
) -> bool:
    """Verify API key from headers"""
    api_key = x_api_key
    
    # Check Authorization header if X-API-Key not provided
    if not api_key and authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]
    
    if not api_key:
        logger.warning("No API key provided")
        raise HTTPException(status_code=401, detail="API key required")
    
    if api_key != settings.api_key:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True


def validate_tenant_access(tenant_id: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate tenant access and return security context"""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID required")
    
    # In a real implementation, validate against user's allowed tenants
    # For now, just return a basic security context
    return {
        "tenant_id": tenant_id,
        "validated": True,
        "user_context": user_context or {}
    }


def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """Sanitize user input to prevent injection attacks"""
    if not text:
        return ""
    
    # Truncate to max length
    text = text[:max_length]
    
    # Remove potentially dangerous patterns
    # In production, use a more sophisticated sanitizer
    dangerous_patterns = ["<script", "javascript:", "onerror=", "onload="]
    text_lower = text.lower()
    
    for pattern in dangerous_patterns:
        if pattern in text_lower:
            logger.warning(f"Potentially dangerous pattern detected: {pattern}")
            text = text.replace(pattern, "")
            text = text.replace(pattern.upper(), "")
    
    return text.strip()