from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.db.database import get_db # SQLAlchemy session
from app.db.models import User # SQLAlchemy User model
from app.services.auth_service import AuthService # AuthService is now SQLAlchemy-based
from app.core.config import settings

# SQLAlchemy-based dependencies

def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> User:
    """
    Gets the current authenticated user from the token.
    Uses SQLAlchemy-based AuthService.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔑 [DEPENDENCIES] get_current_user called with authorization: {'Yes' if authorization else 'No'}")
    
    if not authorization:
        logger.warning("⚠️ No Authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not authorization.startswith("Bearer "):
        logger.warning("⚠️ Invalid Authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    logger.info(f"🔑 [DEPENDENCIES] Extracted token: {token[:20]}...")
    
    try:
        logger.info(f"📞 [DEPENDENCIES] Calling AuthService.verify_clerk_token")
        clerk_payload = AuthService.verify_clerk_token(token=token)
        
        if not clerk_payload or not clerk_payload.get('sub'):
            logger.warning("⚠️ [DEPENDENCIES] Invalid Clerk token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        clerk_user_id = clerk_payload.get('sub')
        logger.info(f"🔍 [DEPENDENCIES] Looking for user with Clerk ID: {clerk_user_id}")
        
        user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
        if not user:
            logger.warning(f"⚠️ [DEPENDENCIES] User not found for Clerk ID: {clerk_user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found. Please sync your account first.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"✅ [DEPENDENCIES] User authenticated: {user.email}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None)
) -> str:
    """
    Gets the ID of the current tenant.
    If the X-Tenant-ID header is present and valid for a superuser, it's used.
    Otherwise, uses the tenant of the current user.
    """
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        # In a multi-tenant mode, allow superusers to override tenant via header
        # Additional validation for x_tenant_id (e.g., checking if tenant exists) could be added here.
        return x_tenant_id
    
    return str(current_user.tenant_id)

def get_current_active_user( # This is a more specific version of get_current_user
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Ensures the current user is active.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

def get_current_active_superuser(
    current_user: User = Depends(get_current_active_user), # Depends on active user check
) -> User:
    """
    Verifies that the current active user has superuser privileges.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user
