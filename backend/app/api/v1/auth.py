# backend/app/api/v1/auth.py
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.user import UserCreate, UserResponse, UserSync, OnboardingComplete
from app.services.auth_service import AuthService
from app.api.dependencies import get_current_user
from app.db.models import User, UserProfile

import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Log que el router se está cargando
logger.info("🚀 Auth router loaded with endpoints: register, sync-user, me, complete-onboarding")

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
) -> Any:
    """
    Create new user without the need to be logged in.
    Only creates regular users, not superusers.
    """
    # Security: Force is_superuser to False for public registration
    user = AuthService.create_user(
        db=db,
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        is_superuser=False,  # Always False for public registration
        tenant_id=str(user_in.tenant_id),
        clerk_user_id=user_in.clerk_user_id
    )
    
    return user

@router.post("/sync-user", response_model=UserResponse, tags=["auth"])
async def sync_user(
    user_data: UserSync,
    db: Session = Depends(get_db)
) -> Any:
    """
    Sync user from Clerk authentication system.
    Creates user if it doesn't exist, updates if it does.
    """
    logger.info(f"🔄 Syncing user from Clerk: {user_data.clerk_user_id}")
    
    # Prepare subscription data if provided
    subscription_data = None
    if user_data.subscription_data:
        subscription_data = {
            'stripe_subscription_id': user_data.subscription_data.stripe_subscription_id,
            'plan_id': user_data.subscription_data.plan_id
        }
    
    user = AuthService.sync_user_from_clerk(
        db=db,
        clerk_user_id=user_data.clerk_user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        stripe_customer_id=user_data.stripe_customer_id,
        subscription_data=subscription_data
    )
    
    logger.info(f"✅ User synced successfully: {user.id}")
    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    logger.info(f"📋 [AUTH_ENDPOINT] /me endpoint reached - user: {current_user.email}")
    return current_user

@router.post("/complete-onboarding", response_model=UserResponse)
async def complete_onboarding(
    onboarding_data: OnboardingComplete = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Mark user onboarding as completed with additional profile data.
    Creates or updates the user profile with extended information.
    """
    try:
        # Update user onboarding status
        current_user.onboarding_completed = True
        
        # Update user with basic information if provided
        if onboarding_data:
            if onboarding_data.first_name and onboarding_data.last_name:
                current_user.full_name = f"{onboarding_data.first_name} {onboarding_data.last_name}"
            
            # Create or update user profile with extended data
            existing_profile = db.query(UserProfile).filter(
                UserProfile.user_id == current_user.id
            ).first()
            
            if existing_profile:
                # Update existing profile
                logger.info(f"🔄 Updating existing profile for user: {current_user.id}")
                existing_profile.phone = onboarding_data.phone
                existing_profile.role = onboarding_data.role
                existing_profile.company_name = onboarding_data.company_name
                existing_profile.industry = onboarding_data.industry
                existing_profile.team_size = onboarding_data.team_size
                existing_profile.use_case = onboarding_data.use_case
                existing_profile.selected_plan = onboarding_data.selected_plan
                existing_profile.payment_interval = onboarding_data.payment_interval
                existing_profile.onboarding_step = onboarding_data.onboarding_step
            else:
                # Create new profile
                logger.info(f"✨ Creating new profile for user: {current_user.id}")
                new_profile = UserProfile(
                    user_id=current_user.id,
                    phone=onboarding_data.phone,
                    role=onboarding_data.role,
                    company_name=onboarding_data.company_name,
                    industry=onboarding_data.industry,
                    team_size=onboarding_data.team_size,
                    use_case=onboarding_data.use_case,
                    selected_plan=onboarding_data.selected_plan,
                    payment_interval=onboarding_data.payment_interval,
                    onboarding_step=onboarding_data.onboarding_step
                )
                db.add(new_profile)
            
            logger.info(f"📝 Saved onboarding profile data for user {current_user.id}: plan={onboarding_data.selected_plan}, step={onboarding_data.onboarding_step}")
        
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"✅ Onboarding completed for user: {current_user.id}")
        return current_user
        
    except Exception as e:
        logger.error(f"Error completing onboarding: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error completing onboarding"
        )

@router.post("/reset-onboarding", response_model=UserResponse)
async def reset_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Reset user onboarding status for testing the new flow.
    TEMPORARY ENDPOINT FOR DEVELOPMENT.
    """
    try:
        # Reset onboarding status
        current_user.onboarding_completed = False
        
        # Delete existing profile if it exists
        existing_profile = db.query(UserProfile).filter(
            UserProfile.user_id == current_user.id
        ).first()
        
        if existing_profile:
            db.delete(existing_profile)
            logger.info(f"🗑️ Deleted existing profile for user: {current_user.id}")
        
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"🔄 Onboarding and profile reset for user: {current_user.id}")
        return current_user
        
    except Exception as e:
        logger.error(f"Error resetting onboarding: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error resetting onboarding"
        )

@router.delete("/dev/delete-user", status_code=204)
async def delete_user_dev(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> None:
    """
    DEVELOPMENT ONLY: Delete current user completely from database.
    WARNING: This will delete ALL user data including documents, subscriptions, etc.
    """
    try:
        logger.warning(f"🚨 [DEV] Deleting user completely: {current_user.id} - {current_user.email}")
        
        # Delete all related data (cascade should handle most, but let's be explicit)
        # Delete user profile
        db.query(UserProfile).filter(UserProfile.user_id == current_user.id).delete()
        
        # Delete user subscriptions
        from app.db.models import Subscription
        db.query(Subscription).filter(Subscription.user_id == current_user.id).delete()
        
        # Delete user image
        from app.db.models import UserImage
        db.query(UserImage).filter(UserImage.user_id == current_user.id).delete()
        
        # Delete the user (this should cascade delete other relationships)
        db.delete(current_user)
        
        db.commit()
        logger.info(f"✅ [DEV] User {current_user.email} deleted completely")
        
    except Exception as e:
        logger.error(f"❌ [DEV] Error deleting user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting user"
        )