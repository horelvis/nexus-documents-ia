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
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Gets the current authenticated user from the token.
    Uses SQLAlchemy-based AuthService.
    """
    user = AuthService.get_current_user(db=db, token=token)
    if not user:
        # AuthService.get_current_user already raises HTTPException if token is invalid or user not found
        # However, an additional check here can be for robustness, though likely redundant
        # if AuthService handles all error cases.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not authenticate user from token", # Generic message if AuthService didn't raise
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

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

# Note: Removed get_prisma_db, api_key_header, and verify_api_key as they were Prisma-related or unused by remaining endpoints.
# Also removed direct Prisma imports.
