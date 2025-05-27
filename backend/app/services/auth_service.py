import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password, get_password_hash
from app.db.models import User, Tenant # SQLAlchemy models
from app.schemas.auth import TokenPayload

logger = logging.getLogger(__name__)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token") # Corrected tokenUrl to point to /auth not /login

class AuthService:
    SECRET_KEY = settings.SECRET_KEY
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    @staticmethod
    def create_access_token(subject: str, tenant_id: str, expires_delta: Optional[timedelta] = None) -> str:
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {
            "exp": expire,
            "iat": datetime.utcnow(),
            "sub": str(subject), # Ensure subject is string
            "tid": str(tenant_id)  # Ensure tenant_id is string
        }
        encoded_jwt = jwt.encode(to_encode, AuthService.SECRET_KEY, algorithm=AuthService.ALGORITHM)
        return encoded_jwt

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @classmethod
    def get_current_user(cls, db: Session, token: str = Depends(oauth2_scheme)) -> Optional[User]:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
            token_data = TokenPayload(**payload)
            if token_data.exp is not None and datetime.fromtimestamp(token_data.exp) < datetime.utcnow():
                raise credentials_exception
        except (JWTError, ValidationError) as e:
            logger.error(f"Token validation error: {e}")
            raise credentials_exception
        
        user = db.query(User).filter(User.id == token_data.sub).first()
        if user is None:
            raise credentials_exception
        # Additional checks like user.is_active can be added here if needed
        # if not user.is_active:
        #     raise HTTPException(status_code=400, detail="Inactive user")
        # if str(user.tenant_id) != token_data.tid:
        #     raise HTTPException(status_code=403, detail="Tenant mismatch")
        return user

    @classmethod
    def get_current_active_user(cls, current_user: User = Depends(get_current_user)) -> User: # Renamed for clarity
        if not current_user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user

    @classmethod
    def get_current_active_superuser(cls, current_user: User = Depends(get_current_user)) -> User: # Depends on the reverted get_current_user
        # Note: get_current_user itself should be wired via dependencies.py to use this AuthService.get_current_user
        # This method is a simple check on the user object provided by the dependency.
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The user doesn't have enough privileges"
            )
        return current_user

    @classmethod
    def create_user(
        cls,
        db: Session,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        tenant_id: Optional[uuid.UUID] = None, # Allow None for default tenant or if tenant creation is separate
        is_superuser: bool = False,
        clerk_user_id: Optional[str] = None # New parameter
    ) -> User:
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        if tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tenant with ID {tenant_id} not found."
                )
        else:
            # Handle cases where tenant_id might be optional or a default is used
            # For now, let's assume if no tenant_id, it's an error or needs specific logic
            # This depends on application requirements. For now, let's make it required for clarity.
            # Or, if users can exist without tenants or belong to a default one, adjust here.
            raise HTTPException(status_code=400, detail="Tenant ID is required to create a user.")

        hashed_password = get_password_hash(password)
        new_user = User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            tenant_id=tenant_id,
            is_superuser=is_superuser,
            is_active=True, # Default to active
            clerk_user_id=clerk_user_id # Add this line
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    @classmethod
    def create_tenant(
        cls,
        db: Session,
        name: str,
        bucket_name: str, # Added as it's non-nullable in SQLAlchemy model
        description: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Tenant:
        existing_tenant = db.query(Tenant).filter(Tenant.name == name).first()
        if existing_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant name already exists"
            )
        
        new_tenant = Tenant(
            name=name,
            description=description,
            bucket_name=bucket_name,
            settings=settings,
            is_active=True # Default to active
        )
        db.add(new_tenant)
        db.commit()
        db.refresh(new_tenant)
        return new_tenant
