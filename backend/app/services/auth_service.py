# backend/app/services/auth_service.py
"""
Authentication service for user management and password operations.

Clerk JWT verification is delegated to the unified auth module.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
import logging

from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.core.auth import (
    verify_clerk_token as _verify_clerk_token,
    AuthError,
    TokenExpiredError,
    TokenInvalidError,
    ClerkConfigError,
)

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



class AuthService:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica que la contraseña coincida con el hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Genera un hash de la contraseña."""
        return pwd_context.hash(password)

    # create_access_token removido - usando Clerk para tokens

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """Autentica un usuario con email y contraseña."""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def create_user(
        db: Session,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        is_superuser: bool = False,
        clerk_user_id: Optional[str] = None
    ) -> User:
        """Crea un nuevo usuario."""
        # Verificar que el email no esté ya registrado
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Crear usuario (single-tenant: no tenant row to reference)
        db_user = User(
            id=uuid4(),
            email=email,
            hashed_password=AuthService.get_password_hash(password),
            full_name=full_name,
            is_superuser=is_superuser,
            clerk_user_id=clerk_user_id
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def verify_clerk_token(token: str) -> dict:
        """
        Verify a Clerk JWT token.

        Delegates to the unified auth module (app.core.auth.clerk).
        Converts AuthError exceptions to HTTPException for API compatibility.

        Args:
            token: JWT token (without 'Bearer ' prefix)

        Returns:
            dict with 'sub' (clerk_user_id), 'iss' (issuer), 'session_id'

        Raises:
            HTTPException: On verification failure
        """
        try:
            return _verify_clerk_token(token)
        except TokenExpiredError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except TokenInvalidError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message,
                headers={"WWW-Authenticate": "Bearer"},
            )
        except ClerkConfigError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Clerk not properly configured",
            )
        except AuthError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=e.message,
                headers={"WWW-Authenticate": "Bearer"},
            )


    @staticmethod
    def sync_user_from_clerk(
        db: Session,
        clerk_user_id: str,
        email: str,
        full_name: str,
        stripe_customer_id: Optional[str] = None
    ) -> User:
        """
        Sync user from Clerk webhook. Creates if not exists, updates if exists.

        Called by Clerk webhook handler on user.created/user.updated events.
        """
        # Find existing user by clerk_user_id
        user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()

        if user:
            # User exists, update if changed
            if user.email != email:
                user.email = email
            if user.full_name != full_name:
                user.full_name = full_name
            if stripe_customer_id and user.stripe_customer_id != stripe_customer_id:
                user.stripe_customer_id = stripe_customer_id

            db.commit()
            db.refresh(user)
            logger.debug(f"Updated user: {str(user.id)[:8]}...")
            return user

        # User doesn't exist, check by email (link existing account)
        user_by_email = db.query(User).filter(User.email == email).first()
        if user_by_email:
            user_by_email.clerk_user_id = clerk_user_id
            user_by_email.full_name = full_name
            if stripe_customer_id:
                user_by_email.stripe_customer_id = stripe_customer_id

            db.commit()
            db.refresh(user_by_email)
            logger.debug(f"Linked existing user by email: {str(user_by_email.id)[:8]}...")
            return user_by_email

        # Single-tenant mode: no tenant row to reference; create the user directly.
        trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)

        new_user = User(
            id=uuid4(),
            email=email,
            hashed_password=AuthService.get_password_hash("clerk_managed_auth"),
            full_name=full_name,
            is_superuser=False,
            clerk_user_id=clerk_user_id,
            stripe_customer_id=stripe_customer_id,
            is_active=True,
            subscription_plan="trial",
            subscription_status="trialing",
            trial_ends_at=trial_end_date
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info(f"Created new user from Clerk: {str(new_user.id)[:8]}...")
        return new_user

