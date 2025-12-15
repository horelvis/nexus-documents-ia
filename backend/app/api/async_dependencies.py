"""
Async dependencies for FastAPI endpoints.

Authentication flow (NO JIT Provisioning):
1. Frontend sends Clerk JWT token in Authorization header
2. Backend validates token with Clerk JWKS (via unified auth module)
3. If user doesn't exist in DB → returns 401 (must register first)
4. Returns authenticated user

User creation is handled by Clerk webhook on user.created event.
Login only validates existing users.
"""
from typing import Optional
import logging
import os

from fastapi import Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.async_database import get_async_db
from app.db.models import User
from app.core.config import settings
from app.core.auth import (
    verify_clerk_token,
    AuthError,
    TokenMissingError,
    TokenExpiredError,
    TokenInvalidError,
    ClerkConfigError,
)

logger = logging.getLogger(__name__)


async def get_current_user_async(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
) -> User:
    """
    Get current authenticated user (NO JIT provisioning).

    Flow:
    1. Validate Clerk token via unified auth module
    2. Find user by clerk_user_id
    3. If not found → return 401 (user must register via SignUp)
    4. Return user

    User creation is handled by Clerk webhook on user.created event.
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    client_host = getattr(getattr(request, "client", None), "host", None)

    # Development mode: Allow X-User-Id header for testing
    if x_user_id and os.getenv("ENVIRONMENT", "development") == "development":
        result = await db.execute(
            select(User).where(User.clerk_user_id == x_user_id).options(selectinload(User.tenant))
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
            return user

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

    # Verify token using unified auth module
    try:
        payload = verify_clerk_token(token)
    except TokenExpiredError:
        logger.info(
            "Auth token expired | method=%s path=%s origin=%s client=%s request_id=%s",
            request.method,
            request.url.path,
            origin,
            client_host,
            x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except TokenInvalidError as e:
        logger.warning(
            "Auth token invalid | method=%s path=%s origin=%s client=%s request_id=%s error=%s",
            request.method,
            request.url.path,
            origin,
            client_host,
            x_request_id,
            e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except ClerkConfigError:
        logger.error(
            "Auth misconfigured (Clerk) | method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service not configured"
        )
    except AuthError as e:
        logger.warning(
            "Auth error | method=%s path=%s origin=%s client=%s request_id=%s status=%s error=%s",
            request.method,
            request.url.path,
            origin,
            client_host,
            x_request_id,
            e.status_code,
            e.message,
        )
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"}
        )

    clerk_user_id = payload.get('sub')

    # Find user
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.image))
        .where(User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    # NO JIT provisioning - user must register via SignUp flow
    if not user:
        logger.warning(
            "Auth attempt for unregistered user | user=%s method=%s path=%s origin=%s client=%s request_id=%s",
            f"{clerk_user_id[:8]}..." if clerk_user_id else None,
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

    return user


async def get_current_tenant_id_async(
    current_user: User = Depends(get_current_user_async),
    x_tenant_id: Optional[str] = Header(None)
) -> str:
    """
    Get the current tenant ID.

    Superusers can override via X-Tenant-ID header in multi-tenant mode.
    """
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        return x_tenant_id

    return str(current_user.tenant_id)


async def get_current_tenant_async(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
    x_tenant_id: Optional[str] = Header(None)
):
    """
    Get the current Tenant object.

    Superusers can override via X-Tenant-ID header in multi-tenant mode.
    """
    from app.db.models import Tenant

    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        result = await db.execute(select(Tenant).where(Tenant.id == x_tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        return tenant

    # Use tenant from current user's relationship if loaded
    if current_user.tenant:
        return current_user.tenant

    # Fallback: query by tenant_id
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tenant not found"
        )

    return tenant


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
    current_user: User = Depends(get_current_user_async)
) -> User:
    """
    Async version that ensures the current user is active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def get_current_active_superuser_async(
    current_user: User = Depends(get_current_active_user_async),
) -> User:
    """
    Async version that verifies superuser privileges
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user


async def get_current_tenant_admin_async(
    current_user: User = Depends(get_current_active_user_async),
) -> User:
    """
    Async version that verifies tenant admin privileges
    """
    if current_user.is_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team administrators can perform this action"
        )
    return current_user


async def require_document_upload_permission_async(
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Async version of document upload permission check
    """
    from app.services.subscription_service_v2 import SubscriptionServiceV2
    
    # Now using async version of SubscriptionServiceV2 methods
    can_upload, error_message = await SubscriptionServiceV2.check_document_permission(db, current_user)
    
    if not can_upload:
        subscription_status = await SubscriptionServiceV2.get_user_subscription_status(db, current_user)
        
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
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """
    Async version of agent permission check
    """
    from app.services.subscription_service_v2 import SubscriptionServiceV2
    
    can_use_agents, error_message = await SubscriptionServiceV2.check_agent_permission(db, current_user)
    
    if not can_use_agents:
        subscription_status = await SubscriptionServiceV2.get_user_subscription_status(db, current_user)
        
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
    """
    Async version of subscription permission dependency
    """
    async def permission_checker(
        current_user: User = Depends(get_current_active_user_async),
        db: AsyncSession = Depends(get_async_db)
    ) -> User:
        from app.services.subscription_service_v2 import SubscriptionServiceV2
        
        can_perform, error_message = await SubscriptionServiceV2.can_user_perform_action(
            db, current_user, permission
        )
        
        if not can_perform:
            subscription_status = await SubscriptionServiceV2.get_user_subscription_status(db, current_user)
            
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Dependency to get an instance of AsyncDocumentService
    """
    from app.services.async_document_service import AsyncDocumentService
    return await AsyncDocumentService.create(
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        db=db
    )
