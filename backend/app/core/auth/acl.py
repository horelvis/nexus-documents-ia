"""Role-based ACL helpers for single-tenant claims-based authorization.

This module replaces the multi-tenant filtering of the previous architecture.
After the multi-tenancy removal refactor, document access is governed by
KeyCloak roles carried in the JWT (via UserProfile.roles) checked against
the per-document `roles` array column.

Two public surfaces:

1. `filter_visible_to_user(query, user)` — apply WHERE clause to a Document
   query so it only returns rows the user is authorized to see.

2. `require_role(*allowed_roles)` — FastAPI dependency that returns the
   current user if they hold any of the listed roles, else 403.

The wildcard role `EVERYONE` is reserved: any document with this role in
its roles[] is visible to every authenticated user regardless of their
individual role list.
"""
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.sql.elements import BooleanClauseList

from app.core.auth.base import UserProfile
from app.api.async_dependencies import get_current_user_async

EVERYONE_ROLE = "EVERYONE"


def build_role_filter_clause(user: UserProfile) -> BooleanClauseList:
    """Build the SQLAlchemy filter clause for role-based document visibility.

    Returns a clause equivalent to:
        documents.roles @> ARRAY['EVERYONE'] OR documents.roles && user_roles

    where the second branch is omitted if the user has no roles.

    This is exposed separately from filter_visible_to_user so unit tests
    can inspect the generated clause without needing a Document model.
    """
    # Late import to avoid circular dependency with app.db.models
    from app.db.models import Document

    clauses = [Document.roles.contains([EVERYONE_ROLE])]
    if user.roles:
        clauses.append(Document.roles.overlap(list(user.roles)))
    return or_(*clauses)


def filter_visible_to_user(query, user: UserProfile):
    """Apply role-based ACL filter to a Document query.

    Replaces every legacy multi-tenant filter on the Document table.

    Args:
        query: A SQLAlchemy query object selecting from Document.
        user: The current authenticated user profile.

    Returns:
        The query with an additional WHERE clause restricting results
        to documents accessible to the user's roles.
    """
    return query.filter(build_role_filter_clause(user))


def require_role(*allowed_roles: str):
    """FastAPI dependency factory that gates endpoints by KeyCloak role.

    Usage:
        @router.get("/admin/things", dependencies=[Depends(require_role("ADMIN"))])
        def list_things(): ...

        # or to receive the user inside the handler:
        @router.get("/legal/contracts")
        def list_contracts(user: UserProfile = Depends(require_role("LEGAL", "ADMIN"))):
            ...

    The wildcard `EVERYONE` is NOT a valid argument here — it is meaningful
    only for documents, not for endpoint authorization. Endpoints that
    should be accessible to any authenticated user should use
    `Depends(get_current_user)` directly without `require_role`.

    Raises:
        HTTPException 403 if the user has none of the listed roles.
    """
    if EVERYONE_ROLE in allowed_roles:
        raise ValueError(
            f"{EVERYONE_ROLE} is not a valid argument to require_role. "
            "Use Depends(get_current_user) for endpoints open to any authenticated user."
        )

    async def _dependency(user: UserProfile = Depends(get_current_user_async)) -> UserProfile:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden: missing required role",
            )
        return user

    return _dependency
