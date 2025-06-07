# backend/app/api/v1/auth.py
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate, UserResponse, UserSync
from app.services.auth_service import AuthService
from app.api.dependencies import get_current_user

import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Log que el router se está cargando
logger.info("🚀 Auth router loaded with endpoints: login, register, sync-user, me")

@router.post("/login/access-token", response_model=TokenResponse)
async def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = AuthService.authenticate_user(
        db=db, email=form_data.username, password=form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    return {
        "access_token": AuthService.create_access_token(
            subject=str(user.id),
            tenant_id=str(user.tenant_id),
            expires_delta=access_token_expires
        ),
        "token_type": "bearer"
    }

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
    
    user = AuthService.sync_user_from_clerk(
        db=db,
        clerk_user_id=user_data.clerk_user_id,
        email=user_data.email,
        full_name=user_data.full_name
    )
    
    logger.info(f"✅ User synced successfully: {user.id}")
    return user

@router.options("/me")
async def options_users_me():
    """
    Handle CORS preflight for /me endpoint
    """
    logger.info("🔄 [OPTIONS] Handling OPTIONS request for /me")
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
        }
    )

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user = Depends(get_current_user)
) -> Any:
    """
    Get current user.
    """
    return current_user

@router.post("/complete-onboarding", response_model=UserResponse)
async def complete_onboarding(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
) -> Any:
    """
    Mark user onboarding as completed.
    """
    try:
        # Update user onboarding status
        current_user.onboarding_completed = True
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"✅ Onboarding completed for user: {current_user.id}")
        return current_user
        
    except Exception as e:
        logger.error(f"Error completing onboarding: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error completing onboarding"
        )