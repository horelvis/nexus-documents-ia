from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.schemas.auth import TokenResponse, UserCreate, User
from app.services.auth_service import AuthService

router = APIRouter()


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


@router.post("/register", response_model=User)
async def register_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = AuthService.create_user(
        db=db,
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
    )
    
    return user


@router.get("/me", response_model=User)
async def read_users_me(
    current_user = Depends(AuthService.get_current_user),
) -> Any:
    """
    Get current user.
    """
    return current_user