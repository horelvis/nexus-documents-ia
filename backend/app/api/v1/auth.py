# backend/app/api/v1/auth.py
"""
Authentication endpoints.

Clerk + Stripe authentication flow:
- POST /login: Validate existing user, return subscription info
- POST /logout: Log the event (Clerk handles session)
- GET /me: Get current user data
- POST /complete-onboarding: Mark onboarding as done
"""
from typing import Optional
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.async_database import get_async_db
from app.api.async_dependencies import get_current_user_async
from app.core.auth import verify_clerk_token, AuthError
from app.db.models import User
from app.schemas.auth import LoginResponse, LogoutResponse, SubscriptionInfo, UserPermissions
from app.services.subscription_service_v2 import SubscriptionServiceV2

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_user(user: User) -> dict:
    """Convert User model to dict for response."""
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "onboarding_completed": user.onboarding_completed,
        "stripe_customer_id": user.stripe_customer_id,
        "tenant_id": str(user.tenant_id),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "subscription_plan": getattr(user, 'subscription_plan', 'trial'),
        "subscription_status": getattr(user, 'subscription_status', 'active'),
        "clerk_user_id": user.clerk_user_id,
        "is_team_member": getattr(user, 'is_team_member', False),
        "is_admin": bool(getattr(user, "is_admin", False)),
        "trial_ends_at": user.trial_ends_at.isoformat() if hasattr(user, 'trial_ends_at') and user.trial_ends_at else None,
    }


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user_async)
) -> dict:
    """
    Get current authenticated user.

    Returns 401 if user doesn't exist in database.
    Use POST /login for initial authentication with subscription data.
    """
    return _serialize_user(current_user)


@router.post("/complete-onboarding")
async def complete_onboarding(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async)
) -> dict:
    """Mark user onboarding as completed."""
    try:
        current_user.onboarding_completed = True
        await db.commit()
        await db.refresh(current_user)

        logger.info(f"✅ Onboarding completed for user: {current_user.id}")
        return _serialize_user(current_user)

    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error completing onboarding"
        )


def _build_permissions(user: User, subscription_status: dict) -> UserPermissions:
    """Build user permissions based on subscription and roles."""
    plan = subscription_status.get('plan', 'trial')

    # Permission mapping by plan
    plan_permissions = {
        'trial': {'can_use_agents': False, 'can_invite_members': False, 'can_access_api': False, 'can_export': False},
        'basic': {'can_use_agents': True, 'can_invite_members': False, 'can_access_api': False, 'can_export': True},
        'pro': {'can_use_agents': True, 'can_invite_members': True, 'can_access_api': True, 'can_export': True},
        'professional': {'can_use_agents': True, 'can_invite_members': True, 'can_access_api': True, 'can_export': True},
        'enterprise': {'can_use_agents': True, 'can_invite_members': True, 'can_access_api': True, 'can_export': True},
    }

    perms = plan_permissions.get(plan, plan_permissions['trial'])

    return UserPermissions(
        is_admin=bool(getattr(user, 'is_admin', False)),
        is_team_member=bool(getattr(user, 'is_team_member', False)),
        can_upload_documents=True,  # All plans can upload
        can_use_agents=subscription_status.get('can_use_agents', perms['can_use_agents']),
        can_invite_members=perms['can_invite_members'],
        can_access_api=perms['can_access_api'],
        can_export=perms['can_export']
    )


def _calculate_needs_upgrade(user: User, subscription_status: dict) -> bool:
    """Check if user needs to upgrade (trial expired without paid plan)."""
    plan = subscription_status.get('plan', 'trial')
    status = subscription_status.get('status', 'unknown')

    # If not on trial, check if subscription is active
    if plan != 'trial':
        return status not in ['active', 'trialing']

    # Check if trial expired
    trial_ends_at = getattr(user, 'trial_ends_at', None)
    if trial_ends_at:
        if isinstance(trial_ends_at, str):
            trial_ends_at = datetime.fromisoformat(trial_ends_at.replace('Z', '+00:00'))

        now = datetime.now(timezone.utc)
        if trial_ends_at.tzinfo is None:
            trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)

        return now > trial_ends_at

    return False


@router.post("/login", response_model=LoginResponse)
async def login(
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> LoginResponse:
    """
    Login endpoint.

    Validates Clerk JWT token and returns user data with subscription info.
    Returns 401 if user doesn't exist (must register first via SignUp).

    This endpoint does NOT create users - registration is handled separately
    by the Clerk webhook on user.created event.
    """
    # 1. Validate Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]

    # 2. Verify Clerk JWT token using unified auth module
    try:
        payload = verify_clerk_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"}
        )

    clerk_user_id = payload.get('sub')
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: no user ID"
        )

    # 3. Find user by clerk_user_id - NO JIT provisioning
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.tenant))
        .where(User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"Login attempt for unregistered clerk_user_id: {clerk_user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not registered. Please sign up first."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    # 4. Get subscription status from Stripe (force refresh on login)
    try:
        subscription_status = await SubscriptionServiceV2.verify_on_login(db, user)
    except Exception as e:
        logger.error(f"Error fetching subscription: {e}")
        # Default to trial status if Stripe fails
        subscription_status = {
            'plan': getattr(user, 'subscription_plan', 'trial'),
            'status': getattr(user, 'subscription_status', 'trialing'),
            'can_use_agents': False,
            'can_use_advanced_features': False,
            'limits': {'documents': 10, 'storage_mb': 100},
            'message': 'Unable to verify subscription'
        }

    # 5. Calculate needs_upgrade flag
    needs_upgrade = _calculate_needs_upgrade(user, subscription_status)

    # 6. Build permissions based on plan
    permissions = _build_permissions(user, subscription_status)

    # 7. Update last_login_at (use utcnow() for TIMESTAMP WITHOUT TIME ZONE column)
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)  # Refresh to avoid lazy loading issues after commit

    # 8. Build subscription info
    trial_days_remaining = None
    trial_ends_at = getattr(user, 'trial_ends_at', None)
    if trial_ends_at and subscription_status.get('plan') == 'trial':
        now = datetime.now(timezone.utc)
        if isinstance(trial_ends_at, str):
            trial_ends_at = datetime.fromisoformat(trial_ends_at.replace('Z', '+00:00'))
        if trial_ends_at.tzinfo is None:
            trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
        days_remaining = (trial_ends_at - now).days
        trial_days_remaining = max(0, days_remaining)

    subscription = SubscriptionInfo(
        plan=subscription_status.get('plan', 'trial'),
        status=subscription_status.get('status', 'trialing'),
        can_use_agents=subscription_status.get('can_use_agents', False),
        can_use_advanced_features=subscription_status.get('can_use_advanced_features', False),
        limits=subscription_status.get('limits', {}),
        needs_upgrade=needs_upgrade,
        trial_days_remaining=trial_days_remaining,
        current_period_end=subscription_status.get('current_period_end'),
        subscription_id=subscription_status.get('subscription_id'),
        cancel_at_period_end=subscription_status.get('cancel_at_period_end', False)
    )

    logger.info(f"✅ Login successful for user {user.id} - Plan: {subscription.plan}")

    return LoginResponse(
        user=_serialize_user(user),
        subscription=subscription,
        permissions=permissions,
        tenant_id=str(user.tenant_id)
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    current_user: User = Depends(get_current_user_async)
) -> LogoutResponse:
    """
    Logout endpoint.

    Logs the logout event for monitoring.
    Clerk handles actual session invalidation on the frontend.
    """
    logger.info(f"👋 User {current_user.id} ({current_user.email}) logged out")

    return LogoutResponse(
        success=True,
        message="Logout successful"
    )
