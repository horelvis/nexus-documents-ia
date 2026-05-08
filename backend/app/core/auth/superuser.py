"""Superuser-only FastAPI dependency.

The single surviving authz dimension after the role-based ACL removal.
Centralizes the ``is_superuser`` gate used across admin endpoints
(agents catalog, weaviate inspection, prompt management). Replaces
both the per-router ``_require_admin`` helpers and the legacy
``require_role`` from ``app/core/auth/acl.py``.

Set ``User.is_superuser=True`` via the manual ``PATCH /users/{id}/role`` flow.
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
