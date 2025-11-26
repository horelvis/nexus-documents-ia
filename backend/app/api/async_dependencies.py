"""
Async versions of common dependencies for use with AsyncSession
"""
from typing import Optional

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.async_database import get_async_db
from app.db.models import User
from app.services.async_auth_service import AsyncAuthService
from app.core.config import settings


async def get_current_user_async(
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> User:
    """
    Async version of get_current_user that works with AsyncSession
    """
    import logging
    import os
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔑 [ASYNC_DEPENDENCIES] get_current_user_async called with authorization: {'Yes' if authorization else 'No'}, X-User-Id: {x_user_id}")
    
    # Development mode: Allow X-User-Id header for testing
    if x_user_id and os.getenv("ENVIRONMENT", "development") == "development":
        logger.info(f"🔧 [ASYNC_DEPENDENCIES] Development mode: Using X-User-Id: {x_user_id}")
        result = await db.execute(
            select(User).where(User.clerk_user_id == x_user_id).options(selectinload(User.tenant))
        )
        user = result.scalar_one_or_none()
        if user:
            logger.info(f"✅ [ASYNC_DEPENDENCIES] Found user via X-User-Id: {user.email}")
            return user
        logger.warning(f"⚠️ User not found with X-User-Id: {x_user_id}")
    
    if not authorization:
        logger.warning("⚠️ No Authorization header provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not authorization.startswith("Bearer "):
        logger.warning("⚠️ Invalid Authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    logger.info(f"🔑 [ASYNC_DEPENDENCIES] Extracted token: {token[:20]}...")
    
    try:
        logger.info(f"📞 [ASYNC_DEPENDENCIES] Calling AsyncAuthService.verify_clerk_token")
        clerk_payload = AsyncAuthService.verify_clerk_token(token=token)
        
        if not clerk_payload or not clerk_payload.get('sub'):
            logger.warning("⚠️ [ASYNC_DEPENDENCIES] Invalid Clerk token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        clerk_user_id = clerk_payload.get('sub')
        logger.info(f"🔍 [ASYNC_DEPENDENCIES] Looking for user with Clerk ID: {clerk_user_id}")
        
        # Use async query
        stmt = select(User).options(
            selectinload(User.roles),
            selectinload(User.image)
        ).filter(User.clerk_user_id == clerk_user_id)
        
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.info(f"👤 [JIT] User not found locally, initiating JIT provisioning for: {clerk_user_id}")
            
            # 1. Fetch Profile from Clerk
            try:
                profile = await AsyncAuthService.fetch_clerk_user_profile(clerk_user_id)
            except Exception as e:
                logger.error(f"❌ [JIT] Failed to fetch Clerk profile: {e}")
                # Fallback to 403 if we can't verify details
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User not registered and provisioning failed.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # 2. Extract Data
            email_addresses = profile.get('email_addresses', [])
            primary_email_id = profile.get('primary_email_address_id')
            email = next((e['email_address'] for e in email_addresses if e['id'] == primary_email_id), None)
            
            if not email and email_addresses:
                email = email_addresses[0]['email_address']
            
            if not email:
                logger.error("❌ [JIT] No email found in Clerk profile")
                raise HTTPException(status_code=400, detail="User has no email")

            full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            if not full_name:
                full_name = email.split('@')[0]
            
            # 3. Create User (Sync)
            # Note: We pass metadata (which contains selected_plan from unsafe_metadata)
            # unsafe_metadata is usually top level in User object from Clerk API
            unsafe_metadata = profile.get('unsafe_metadata', {})
            
            user = await AsyncAuthService.sync_user_from_clerk(
                db=db,
                clerk_user_id=clerk_user_id,
                email=email,
                full_name=full_name,
                metadata=unsafe_metadata
            )
            
            # 4. Ensure Stripe Customer (Critical for SubscriptionService)
            try:
                from app.services.subscription_service_v2 import SubscriptionServiceV2
                await SubscriptionServiceV2._find_or_create_stripe_customer(db, user)
            except Exception as e:
                logger.warning(f"⚠️ [JIT] Failed to setup Stripe customer (non-critical): {e}")
            
            logger.info(f"✅ [JIT] User successfully provisioned: {user.id}")
        
        logger.info(f"✅ [ASYNC_DEPENDENCIES] User authenticated: {user.email}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
