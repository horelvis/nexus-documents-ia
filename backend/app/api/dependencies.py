from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.db.database import get_db # SQLAlchemy session
from app.db.models import User # SQLAlchemy User model
from app.services.auth_service import AuthService, oauth2_scheme # AuthService is now SQLAlchemy-based
from app.core.config import settings

# SQLAlchemy-based dependencies

def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> User:
    """
    Gets the current authenticated user from the token.
    Uses SQLAlchemy-based AuthService.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔐 [DEPENDENCIES] Starting authentication in get_current_user")
    logger.info(f"🎫 [DEPENDENCIES] Token received: {'YES' if token else 'NO'}")
    logger.info(f"🎫 [DEPENDENCIES] Token length: {len(token) if token else 0}")
    logger.info(f"🎫 [DEPENDENCIES] Token prefix: {token[:20]}..." if token else "NO TOKEN")
    
    # Handle case where no token is provided (e.g., OPTIONS requests)
    if not token:
        logger.warning(f"⚠️ [DEPENDENCIES] No token provided - likely OPTIONS request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user = AuthService.get_current_user(db=db, token=token)
        if not user:
            logger.error(f"❌ [DEPENDENCIES] AuthService returned None user")
            # AuthService.get_current_user already raises HTTPException if token is invalid or user not found
            # However, an additional check here can be for robustness, though likely redundant
            # if AuthService handles all error cases.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not authenticate user from token", # Generic message if AuthService didn't raise
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"✅ [DEPENDENCIES] User authenticated successfully: {user.id}")
        logger.info(f"👤 [DEPENDENCIES] User email: {user.email}")
        logger.info(f"🏢 [DEPENDENCIES] User tenant: {user.tenant_id}")
        logger.info(f"🔑 [DEPENDENCIES] User Clerk ID: {user.clerk_user_id}")
        return user
        
    except HTTPException as e:
        logger.error(f"❌ [DEPENDENCIES] HTTPException during auth: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ [DEPENDENCIES] Unexpected error during auth: {str(e)}")
        logger.error(f"🐛 [DEPENDENCIES] Exception type: {type(e)}")
        import traceback
        logger.error(f"📚 [DEPENDENCIES] Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed unexpectedly",
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
