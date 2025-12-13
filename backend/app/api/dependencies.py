"""
DEPRECATED: Legacy sync dependencies module.

This module is maintained for backward compatibility with:
- Existing tests (conftest.py)
- Sync services (GoogleDriveTokenService, template_edit_session_service)

New code should use:
- app.api.async_dependencies for async endpoints
- app.db.database.get_db for sync database sessions
- app.core.auth for Clerk token verification

Migration path:
- Replace `get_current_user` with `get_current_user_async` from async_dependencies
- Replace `get_current_active_user` with `get_current_active_user_async`
- Use `get_db` from app.db.database directly for sync services
"""
import warnings
from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.core.config import settings
from app.core.auth import verify_clerk_token, AuthError

# Re-export for compatibility
__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "get_current_active_superuser",
    "get_current_tenant_id",
    "get_current_tenant",
    "get_current_tenant_admin",
    "require_microservice_api_key",
    "require_admin_role",
]


def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> User:
    """
    DEPRECATED: Use get_current_user_async from async_dependencies.

    Gets the current authenticated user (sync version for legacy code).
    """
    # Development helper: allow X-User-Id override
    if settings.DEBUG and x_user_id:
        from sqlalchemy.orm import selectinload
        user = (
            db.query(User)
            .options(selectinload(User.roles), selectinload(User.image))
            .filter(User.clerk_user_id == x_user_id)
            .first()
        )
        if user:
            return user

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ")[1]

    try:
        payload = verify_clerk_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    clerk_user_id = payload.get('sub')

    from sqlalchemy.orm import selectinload
    user = db.query(User).options(
        selectinload(User.roles),
        selectinload(User.image)
    ).filter(User.clerk_user_id == clerk_user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not registered. Please sign up first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None)
) -> str:
    """DEPRECATED: Use get_current_tenant_id_async from async_dependencies."""
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        return x_tenant_id
    return str(current_user.tenant_id)


def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_tenant_id: Optional[str] = Header(None)
):
    """DEPRECATED: Use get_current_tenant_async from async_dependencies."""
    from app.db.models import Tenant

    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        return tenant

    if current_user.tenant:
        return current_user.tenant

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tenant not found"
        )

    return tenant


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """DEPRECATED: Use get_current_active_user_async from async_dependencies."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


def require_microservice_api_key(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Validate internal microservice calls using the shared API key.

    Accepts both:
    - Authorization: Bearer <api_key> (legacy)
    - X-API-Key: <api_key> (preferred)
    """
    api_key = None

    if x_api_key:
        api_key = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        api_key = authorization.split(" ")[1]

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Use X-API-Key header.",
        )

    if api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid microservice API key",
        )

    return api_key


def get_current_active_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """DEPRECATED: Use get_current_active_superuser_async from async_dependencies."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user


def get_current_tenant_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """DEPRECATED: Use get_current_tenant_admin_async from async_dependencies."""
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team administrators can perform this action"
        )
    return current_user


def require_admin_role(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensures the current user has admin privileges."""
    if getattr(current_user, "is_admin", False):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrative privileges required",
    )
