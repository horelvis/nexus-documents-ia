"""Authorization dependency for admin-gated endpoints.

The single surviving authz dimension after the role-based ACL removal.
Set User.is_superuser=True via the manual PATCH /users/{id}/role flow.
"""
from fastapi import Depends, HTTPException, status

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile


def require_superuser(user: UserProfile = Depends(get_current_user_async)) -> UserProfile:
    """FastAPI dependency that 403s non-superuser callers."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return user
