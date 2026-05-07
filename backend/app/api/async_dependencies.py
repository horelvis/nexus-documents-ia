"""
Async dependencies for FastAPI endpoints.

After the multi-tenancy removal refactor (Plan 2), `get_current_user_async`
returns a `UserProfile` (a request-scoped immutable DTO carrying sub,
email, name, and the canonical KeyCloak roles obtained via
`AuthProvider.map_groups_to_roles()`). Endpoints that need the
SQLAlchemy `User` row (e.g. for FK joins in their own queries) should
look it up explicitly via the User table using `user.sub`.

Tenant-related dependencies and the role-based admin checks were
removed. Use `require_role` from `app.core.auth.acl` for admin gating.

Authentication flow:
- On-premise mode: OIDC/SAML/LDAP token validation via AuthProviderFactory

User lookup:
- On-premise: by sso_external_id
"""
from typing import Optional, List
import logging
import os

from fastapi import Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.async_database import get_async_db
from app.db.models import User
from app.core.config import settings
from app.core.auth.base import UserProfile

logger = logging.getLogger(__name__)


def _build_profile(user: User, sso_roles: Optional[List[str]] = None) -> UserProfile:
    """Build a UserProfile DTO from the SQLAlchemy User row.

    `sso_roles` is the canonical role list from the SSO provider after
    `map_groups_to_roles()`.

    The 'EVERYONE' wildcard is stripped defensively — it must never
    appear in UserProfile.roles (it is for documents only).
    """
    if sso_roles is None:
        roles = ["ADMIN"] if user.is_superuser else []
    else:
        roles = [r for r in sso_roles if r != "EVERYONE"]
        if user.is_superuser and "ADMIN" not in roles:
            roles.append("ADMIN")
    return UserProfile(
        sub=str(user.id),
        email=user.email,
        name=user.full_name,
        roles=roles,
        is_superuser=bool(user.is_superuser),
    )


async def get_current_user_async(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
) -> UserProfile:
    """
    Get current authenticated user as a UserProfile DTO.

    Flow:
    1. Validate token via the deployment's AuthProvider (OIDC/SAML/LDAP).
    2. Find User row by external id (sso_external_id or clerk_user_id).
    3. If not found → 401 (user must register via SignUp).
    4. Build UserProfile with roles derived from SSO groups.

    User creation is handled by the SSO login endpoint. No JIT
    provisioning here.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    client_host = getattr(getattr(request, "client", None), "host", None)

    # Development mode: Allow X-User-Id header for testing
    if x_user_id and os.getenv("ENVIRONMENT", "development") == "development":
        result = await db.execute(
            select(User).where(User.clerk_user_id == x_user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            logger.info(
                "Auth bypass via X-User-Id (dev only) | method=%s path=%s origin=%s client=%s request_id=%s",
                request.method,
                request.url.path,
                origin,
                client_host,
                x_request_id,
            )
            sso_roles = list(user.sso_groups or [])
            return _build_profile(user, sso_roles=sso_roles)

    # Require Authorization header
    if not authorization:
        logger.warning(
            "Missing Authorization header | method=%s path=%s origin=%s referer=%s client=%s request_id=%s",
            request.method,
            request.url.path,
            origin,
            referer,
            client_host,
            x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not authorization.startswith("Bearer "):
        logger.warning(
            "Invalid Authorization header format | method=%s path=%s origin=%s client=%s request_id=%s",
            request.method,
            request.url.path,
            origin,
            client_host,
            x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]

    # Verify token through the configured on-premise provider.
    user_external_id: Optional[str] = None
    sso_role_list: Optional[List[str]] = None
    try:
        from app.core.auth.factory import AuthProviderFactory
        from app.core.auth.exceptions import TokenExpiredError as SSOTokenExpired
        from app.core.auth.exceptions import TokenInvalidError as SSOTokenInvalid

        provider = await AuthProviderFactory.get_default()
        identity = await provider.verify_token(token)
        user_external_id = identity.external_id
        # Map raw SSO groups to canonical role identifiers.
        sso_role_list = provider.map_groups_to_roles(identity.groups or [])
        logger.debug(f"SSO token verified for user: {user_external_id[:8]}...")

    except SSOTokenExpired:
        logger.info(
            "SSO token expired | method=%s path=%s origin=%s client=%s request_id=%s",
            request.method, request.url.path, origin, client_host, x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except SSOTokenInvalid as e:
        logger.warning(
            "SSO token invalid | method=%s path=%s origin=%s client=%s request_id=%s error=%s",
            request.method, request.url.path, origin, client_host, x_request_id, str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        logger.error(f"SSO auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"}
        )

    result = await db.execute(
        select(User).where(User.sso_external_id == user_external_id)
    )
    user = result.scalar_one_or_none()

    # NO JIT provisioning - user must register via the SSO login endpoint.
    if not user:
        logger.warning(
            "Auth attempt for unregistered user | user=%s method=%s path=%s origin=%s client=%s request_id=%s",
            f"{user_external_id[:8]}..." if user_external_id else None,
            request.method,
            request.url.path,
            origin,
            client_host,
            x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not registered. Please sign up first.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return _build_profile(user, sso_roles=sso_role_list)


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


async def get_current_active_user_async(
    current_user: UserProfile = Depends(get_current_user_async),
) -> UserProfile:
    """
    Pass-through after the multi-tenancy refactor.

    The legacy `is_active` soft-delete flag is no longer enforced here:
    KeyCloak handles user status. If the user authenticated successfully
    they are active. This dependency exists only for callers that haven't
    been migrated to depend directly on `get_current_user_async`.
    """
    return current_user


async def require_document_upload_permission_async(
    current_user: UserProfile = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> UserProfile:
    """
    Async version of document upload permission check.

    NOTE: SubscriptionServiceV2 still expects a SQLAlchemy User. Until
    that service is migrated (Plan 2 Task 12), we look up the User row
    by sub and pass it through.
    """
    from app.services.subscription_service_v2 import SubscriptionServiceV2

    user_row = (
        await db.execute(select(User).where(User.id == current_user.sub))
    ).scalar_one_or_none()
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    can_upload, error_message = await SubscriptionServiceV2.check_document_permission(db, user_row)

    if not can_upload:
        subscription_status = await SubscriptionServiceV2.get_user_subscription_status(db, user_row)

        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if subscription_status["plan"] == "free" else status.HTTP_403_FORBIDDEN,
            detail={
                "message": error_message,
                "subscription_status": subscription_status,
                "action_required": "upgrade_plan" if subscription_status["plan"] == "free" else "check_subscription",
                "limits": subscription_status.get("limits", {})
            }
        )

    return current_user


async def require_agent_permission_async(
    current_user: UserProfile = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> UserProfile:
    """Async version of agent permission check (see SubscriptionServiceV2 note above)."""
    from app.services.subscription_service_v2 import SubscriptionServiceV2

    user_row = (
        await db.execute(select(User).where(User.id == current_user.sub))
    ).scalar_one_or_none()
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    can_use_agents, error_message = await SubscriptionServiceV2.check_agent_permission(db, user_row)

    if not can_use_agents:
        subscription_status = await SubscriptionServiceV2.get_user_subscription_status(db, user_row)

        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED if subscription_status["plan"] == "free" else status.HTTP_403_FORBIDDEN,
            detail={
                "message": error_message,
                "subscription_status": subscription_status,
                "action_required": "upgrade_plan" if subscription_status["plan"] == "free" else "check_subscription",
                "limits": subscription_status.get("limits", {})
            }
        )

    return current_user


def require_subscription_permission_async(permission: str):
    """Async subscription permission dependency factory (see SubscriptionServiceV2 note above)."""
    async def permission_checker(
        current_user: UserProfile = Depends(get_current_active_user_async),
        db: AsyncSession = Depends(get_async_db)
    ) -> UserProfile:
        from app.services.subscription_service_v2 import SubscriptionServiceV2

        user_row = (
            await db.execute(select(User).where(User.id == current_user.sub))
        ).scalar_one_or_none()
        if user_row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        can_perform, error_message = await SubscriptionServiceV2.can_user_perform_action(
            db, user_row, permission
        )

        if not can_perform:
            subscription_status = await SubscriptionServiceV2.get_user_subscription_status(db, user_row)

            if subscription_status["plan"] == "free":
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "message": error_message,
                        "subscription_status": subscription_status,
                        "action_required": "reactivate_subscription"
                    }
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "message": error_message,
                        "subscription_status": subscription_status,
                        "action_required": "upgrade_plan"
                    }
                )

        return current_user

    return permission_checker


async def get_document_service(
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """Dependency to get an instance of AsyncDocumentService."""
    from app.services.async_document_service import AsyncDocumentService
    return await AsyncDocumentService.create(user=current_user, db=db)
