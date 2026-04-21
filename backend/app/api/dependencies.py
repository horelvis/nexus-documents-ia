"""
DEPRECATED: Legacy sync dependencies module.

This module is maintained for backward compatibility with sync services
(GoogleDriveTokenService, template_edit_session_service). New code should
use `app.api.async_dependencies` instead.

After the multi-tenancy removal refactor (Plan 2), `get_current_user`
returns a `UserProfile` (a request-scoped immutable DTO carrying sub,
email, name, and the canonical KeyCloak roles). Endpoints that need the
SQLAlchemy `User` row (e.g. for FK joins in their own queries) should
look it up explicitly via `db.query(User).filter(User.id == user.sub)`.

Tenant-related dependencies were removed entirely. Use `require_role`
from `app.core.auth.acl` for admin gating.
"""
import warnings
from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.core.config import settings
from app.core.auth import verify_clerk_token, AuthError
from app.core.auth.base import UserProfile

# Re-export for compatibility
__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "require_microservice_api_key",
]


def _user_to_profile(user: User) -> UserProfile:
    """Build a UserProfile DTO from the SQLAlchemy User row.

    Sync legacy path: Clerk SaaS mode does not carry KeyCloak roles, so
    the profile gets `roles=['ADMIN']` if `is_superuser`, else `[]`. The
    real role mapping happens in the async path through SSO groups.
    """
    roles = ["ADMIN"] if user.is_superuser else []
    return UserProfile(
        sub=str(user.id),
        email=user.email,
        name=user.full_name,
        roles=roles,
    )


def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> UserProfile:
    """
    DEPRECATED: Use get_current_user_async from async_dependencies.

    Sync version. Returns a UserProfile (not a SQLAlchemy User).
    Validates the Clerk token, looks up the User row, then converts to
    a UserProfile DTO.
    """
    # Development helper: allow X-User-Id override
    if settings.DEBUG and x_user_id:
        user = (
            db.query(User)
            .filter(User.clerk_user_id == x_user_id)
            .first()
        )
        if user:
            return _user_to_profile(user)

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

    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not registered. Please sign up first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _user_to_profile(user)


def get_current_active_user(
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """DEPRECATED: Use get_current_active_user_async from async_dependencies.

    Pass-through after the multi-tenancy refactor: the legacy `is_active`
    soft-delete flag is no longer enforced here. KeyCloak handles user
    status; if the user authenticated successfully they are active.
    """
    return current_user


def require_microservice_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    Validate internal microservice calls using the shared API key.

    Internal auth standard: X-API-Key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Use X-API-Key header.",
        )

    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid microservice API key",
        )

    return x_api_key
