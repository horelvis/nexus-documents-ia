"""Superuser-only FastAPI dependency.

Centralizes the `is_superuser` gate used across admin endpoints
(agents catalog, weaviate inspection, prompt management). Replaces
the per-router `_require_admin` helpers that proliferated after
commit 940a3460.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile


async def require_superuser(
    current_user: UserProfile = Depends(get_current_user_async),
) -> UserProfile:
    """Return the current user if they are a superuser, else raise 403.

    Use as ``Depends(require_superuser)`` on every admin-only route.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires a superuser account.",
        )
    return current_user
