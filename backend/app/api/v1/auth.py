# backend/app/api/v1/auth.py
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_database import get_async_db
from app.schemas.user import UserCreate, UserResponse, UserSync, OnboardingComplete
from app.services.async_auth_service import AsyncAuthService
from app.api.async_dependencies import get_current_user_async
from app.db.models import User
from app.core.config import settings

import logging
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter()

# Log que el router se está cargando
logger.info("🚀 Auth router loaded with endpoints: register, sync-user, me, complete-onboarding")

# Helper function to serialize user without lazy-loaded relationships
def serialize_user(user: User) -> dict:
    """Convert User model to dict avoiding lazy-loaded relationships."""
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
        "trial_ends_at": user.trial_ends_at.isoformat() if hasattr(user, 'trial_ends_at') and user.trial_ends_at else None,
        # Omit image and roles to avoid lazy loading issues
        "image": None,
        "roles": []
    }

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_async_db),
) -> Any:
    """
    Create new user without the need to be logged in.
    Only creates regular users, not superusers.
    """
    # Security: Force is_superuser to False for public registration
    user = await AsyncAuthService.create_user(
        db=db,
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        is_superuser=False,  # Always False for public registration
        tenant_id=str(user_in.tenant_id),
        clerk_user_id=user_in.clerk_user_id
    )
    
    return user

@router.post("/sync-user", tags=["auth"])
async def sync_user(
    user_data: UserSync,
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Sync user from Clerk authentication system.
    Creates user if it doesn't exist, updates if it does.
    """
    logger.info(f"🔄 Syncing user from Clerk: {user_data.clerk_user_id}")
    
    user = await AsyncAuthService.sync_user_from_clerk(
        db=db,
        clerk_user_id=user_data.clerk_user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        stripe_customer_id=user_data.stripe_customer_id,
        metadata={
            'selected_plan': user_data.dict().get('selected_plan', 'free')
        }
    )
    
    logger.info(f"✅ User synced successfully: {user.id}")
    
    # Return user data without lazy-loaded relationships
    return serialize_user(user)


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Get current authenticated user information with subscription details."""
    logger.info(f"📋 [AUTH_ENDPOINT] /me endpoint reached - user: {current_user.email}")
    
    # Log user status for debugging
    logger.info(f"📋 [AUTH_ENDPOINT] User onboarding completed: {current_user.onboarding_completed}")
    
    # TODO: Fix SubscriptionServiceV2 to be fully async
    # For now, use the values from the database
    try:
        # Ensure user has default subscription values
        if not current_user.subscription_plan:
            current_user.subscription_plan = 'trial'
        if not current_user.subscription_status:
            current_user.subscription_status = 'active'
        
        # If user has trial_ends_at, check if it's still valid
        if hasattr(current_user, 'trial_ends_at') and current_user.trial_ends_at:
            from datetime import datetime
            if current_user.trial_ends_at < datetime.utcnow():
                # Trial expired
                current_user.subscription_status = 'expired'
        
        await db.commit()
        
    except Exception as e:
        logger.error(f"Error updating subscription status: {e}")
        await db.rollback()
    
    # Return user data without lazy-loaded relationships
    return serialize_user(current_user)


@router.post("/complete-onboarding")
async def complete_onboarding(
    onboarding_data: OnboardingComplete = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async)
) -> dict:
    """
    Mark user onboarding as completed. 
    Datos de perfil se obtienen de Clerk y Stripe, no necesitamos duplicarlos.
    """
    try:
        # Update user onboarding status
        current_user.onboarding_completed = True
        
        # Update user with basic information if provided
        if onboarding_data:
            if onboarding_data.first_name and onboarding_data.last_name:
                current_user.full_name = f"{onboarding_data.first_name} {onboarding_data.last_name}"
            
            # Solo loguear datos adicionales para referencia, no guardarlos
            # Los datos de perfil se obtienen de Clerk
            # Los datos de plan se obtienen de Stripe
            logger.info(f"📝 Onboarding completed for user {current_user.id}")
            logger.info(f"  - Plan seleccionado: {onboarding_data.selected_plan}")
            logger.info(f"  - Empresa: {onboarding_data.company_name}")
            logger.info(f"  - Industria: {onboarding_data.industry}")
            logger.info(f"  - Datos disponibles en Clerk y Stripe")
        
        await db.commit()
        await db.refresh(current_user)
        
        logger.info(f"✅ Onboarding completed for user: {current_user.id}")
        return serialize_user(current_user)
        
    except Exception as e:
        logger.error(f"Error completing onboarding: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error completing onboarding"
        )

@router.post("/reset-onboarding", response_model=UserResponse)
async def reset_onboarding(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async)
) -> Any:
    """
    Reset user onboarding status for testing the new flow.
    TEMPORARY ENDPOINT FOR DEVELOPMENT.
    """
    try:
        # Reset onboarding status
        current_user.onboarding_completed = False
        
        await db.commit()
        await db.refresh(current_user)
        
        logger.info(f"🔄 Onboarding reset for user: {current_user.id}")
        return serialize_user(current_user)
        
    except Exception as e:
        logger.error(f"Error resetting onboarding: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resetting onboarding"
        )

@router.delete("/dev/delete-user", status_code=204)
async def delete_user_dev(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async)
) -> None:
    """
    DEVELOPMENT ONLY: Delete current user completely from database.
    WARNING: This will delete ALL user data including documents, subscriptions, etc.
    """
    try:
        logger.warning(f"🚨 [DEV] Deleting user completely: {current_user.id} - {current_user.email}")
        
        # Delete all related data (cascade should handle most, but let's be explicit)
        # Delete user subscriptions
        from app.db.models import Subscription
        from sqlalchemy import delete
        
        await db.execute(delete(Subscription).where(Subscription.user_id == current_user.id))
        
        # Delete user image
        from app.db.models import UserImage
        await db.execute(delete(UserImage).where(UserImage.user_id == current_user.id))
        
        # Delete the user (this should cascade delete other relationships like documents)
        await db.delete(current_user)
        
        await db.commit()
        logger.info(f"✅ [DEV] User {current_user.email} deleted completely")
        
    except Exception as e:
        logger.error(f"❌ [DEV] Error deleting user: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user"
        )