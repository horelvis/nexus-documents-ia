"""
Async dependencies for FastAPI endpoints.

Authentication flow (NO JIT Provisioning):
1. Frontend sends Clerk JWT token in Authorization header
2. Backend validates token with Clerk JWKS
3. If user doesn't exist in DB → returns 401 (must register first)
4. Returns authenticated user

User creation is handled by Clerk webhook on user.created event.
Login only validates existing users.
"""
from typing import Optional
from datetime import datetime, timedelta
from uuid import uuid4
import logging
import os

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.async_database import get_async_db
from app.db.models import User, Tenant
from app.core.config import settings

logger = logging.getLogger(__name__)


def _verify_clerk_token(token: str) -> dict:
    """
    Verify Clerk JWT token using JWKS.
    Returns payload with 'sub' (clerk_user_id) and email claims.
    """
    import jwt
    from jwt import PyJWKClient

    if not settings.CLERK_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clerk not configured"
        )

    try:
        # Decode without verification to get issuer
        unverified = jwt.decode(token, options={"verify_signature": False})
        issuer = unverified.get('iss', '')

        if not issuer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no issuer"
            )

        # Verify with JWKS
        jwks_client = PyJWKClient(f"{issuer}/.well-known/jwks.json")
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


async def _create_user_jit(db: AsyncSession, clerk_user_id: str, email: str, full_name: str) -> User:
    """
    Just-In-Time user provisioning.
    Creates tenant + user when a valid Clerk user first accesses the system.
    """
    logger.info(f"🆕 JIT provisioning new user: {email}")

    # Create tenant for new user
    tenant_name = email.split('@')[0].replace('.', '-')
    tenant = Tenant(
        id=uuid4(),
        name=f"{tenant_name}-org",
        bucket_name=f"nexus-{tenant_name}-{uuid4().hex[:8]}",
        is_active=True
    )
    db.add(tenant)

    # Create user with trial
    user = User(
        id=uuid4(),
        email=email,
        full_name=full_name or email.split('@')[0],
        clerk_user_id=clerk_user_id,
        tenant_id=tenant.id,
        is_active=True,
        is_superuser=False,
        onboarding_completed=False,
        subscription_plan='trial',
        subscription_status='trialing',
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
        hashed_password="clerk_managed"
    )
    db.add(user)

    await db.commit()
    await db.refresh(user)

    logger.info(f"✅ Created user {user.id} with tenant {tenant.id}")
    return user


async def get_current_user_async(
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> User:
    """
    Get current authenticated user (NO JIT provisioning).

    Flow:
    1. Validate Clerk token
    2. Find user by clerk_user_id
    3. If not found → return 401 (user must register via SignUp)
    4. Return user

    User creation is handled by Clerk webhook on user.created event.
    """
    # Development mode: Allow X-User-Id header for testing
    if x_user_id and os.getenv("ENVIRONMENT", "development") == "development":
        result = await db.execute(
            select(User).where(User.clerk_user_id == x_user_id).options(selectinload(User.tenant))
        )
        user = result.scalar_one_or_none()
        if user:
            return user

    # Require Authorization header
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]

    # Verify token
    payload = _verify_clerk_token(token)
    clerk_user_id = payload.get('sub')

    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: no user ID"
        )

    # Find user
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.image))
        .where(User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    # NO JIT provisioning - user must register via SignUp flow
    if not user:
        logger.warning(f"Auth attempt for unregistered clerk_user_id: {clerk_user_id}")
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
    Async version of get_current_tenant_id
    """
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        return x_tenant_id
    
    return str(current_user.tenant_id)


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
