# backend/app/services/auth_service.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
from uuid import uuid4

from fastapi import HTTPException, status
# Removido jose - usando clerk-backend-api para JWT
from passlib.context import CryptContext
from sqlalchemy.orm import Session
# requests y json removidos - no se usan

from app.core.config import settings
from app.db.models import User, Tenant
# TokenPayload removido - ya no se usa JWT interno

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
        tenant_id: Optional[str] = None,
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
        
        # Si no se proporciona tenant_id, usar el tenant por defecto
        if not tenant_id:
            default_tenant = db.query(Tenant).filter(
                Tenant.name == settings.DEFAULT_TENANT
            ).first()
            if not default_tenant:
                raise HTTPException(
                    status_code=500,
                    detail="Default tenant not found"
                )
            tenant_id = str(default_tenant.id)
        
        # Verificar que el tenant existe
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail="Tenant not found"
            )
        
        # Crear usuario
        db_user = User(
            id=uuid4(),
            email=email,
            hashed_password=AuthService.get_password_hash(password),
            full_name=full_name,
            is_superuser=is_superuser,
            tenant_id=tenant_id,
            clerk_user_id=clerk_user_id
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def create_tenant(
        db: Session,
        name: str,
        description: Optional[str] = None,
        settings: Optional[dict] = None
    ) -> Tenant:
        """Crea un nuevo tenant."""
        # Generar bucket name único para el tenant (organización)
        sanitized_name = name.lower().replace(' ', '-').replace('_', '-')
        bucket_name = f"{sanitized_name}-{uuid4().hex[:8]}"
        
        db_tenant = Tenant(
            id=uuid4(),
            name=name,
            description=description,
            bucket_name=bucket_name,
            settings=settings or {}
        )
        
        db.add(db_tenant)
        db.commit()
        db.refresh(db_tenant)
        return db_tenant

    @staticmethod
    def verify_clerk_token(token: str) -> dict:
        """Verifica un token de Clerk usando JWT verification."""
        import logging
        import jwt
        from jwt import PyJWKClient
        
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"🔍 [VERIFY_CLERK_TOKEN] Starting verification (length: {len(token) if token else 0})")
            
            if not settings.CLERK_SECRET_KEY:
                logger.error("❌ [VERIFY_CLERK_TOKEN] CLERK_SECRET_KEY not configured")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Clerk not properly configured",
                )
            
            if not token:
                logger.error("❌ [VERIFY_CLERK_TOKEN] No token provided")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No token provided",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Use Clerk's JWKS endpoint to verify the token
            # The JWKS URL for Clerk is typically: https://api.clerk.com/v1/jwks
            logger.info("🏗️ [VERIFY_CLERK_TOKEN] Setting up JWT verification...")
            
            # For Clerk, we need to get the issuer from the token first to construct the JWKS URL
            # Decode without verification first to get the issuer
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            issuer = unverified_payload.get('iss', '')
            
            if not issuer:
                logger.error("❌ [VERIFY_CLERK_TOKEN] No issuer in token")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token format",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Construct JWKS URL from issuer
            jwks_url = f"{issuer}/.well-known/jwks.json"
            logger.info(f"🔑 [VERIFY_CLERK_TOKEN] Using JWKS URL: {jwks_url}")
            
            # Create JWKS client and verify token
            jwks_client = PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            
            # Verify and decode the token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False}  # Clerk tokens don't always have audience
            )
            
            logger.info(f"🔍 [VERIFY_CLERK_TOKEN] Token payload: {payload}")
            
            # Extract user information
            user_id = payload.get('sub')
            session_id = payload.get('sid')
            
            if user_id:
                logger.info(f"✅ [VERIFY_CLERK_TOKEN] Token verified for user: {user_id}")
                return {
                    'sub': user_id,
                    'session_id': session_id,
                    'iss': issuer
                }
            else:
                logger.error("❌ [VERIFY_CLERK_TOKEN] No user_id in token")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No user ID in token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                
        except jwt.ExpiredSignatureError:
            logger.error("❌ [VERIFY_CLERK_TOKEN] Token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.error(f"❌ [VERIFY_CLERK_TOKEN] Invalid token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {str(e)}",
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
        """Sincroniza un usuario desde Clerk. Crea si no existe, actualiza si existe."""
        import logging
        logger = logging.getLogger(__name__)
        
        # Buscar usuario existente por clerk_user_id
        user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
        
        if user:
            # Usuario existe, actualizar información si ha cambiado
            logger.info(f"🔄 Updating existing user: {user.id}")
            if user.email != email:
                user.email = email
            if user.full_name != full_name:
                user.full_name = full_name
            if stripe_customer_id and user.stripe_customer_id != stripe_customer_id:
                user.stripe_customer_id = stripe_customer_id
            
            
            db.commit()
            db.refresh(user)
            return user
        
        # Usuario no existe, verificar si existe por email
        user_by_email = db.query(User).filter(User.email == email).first()
        if user_by_email:
            # Usuario existe por email pero sin clerk_user_id, actualizar
            logger.info(f"🔗 Linking existing user by email: {user_by_email.id}")
            user_by_email.clerk_user_id = clerk_user_id
            user_by_email.full_name = full_name
            if stripe_customer_id:
                user_by_email.stripe_customer_id = stripe_customer_id
            
            
            db.commit()
            db.refresh(user_by_email)
            return user_by_email
        
        # Usuario no existe, crear uno nuevo
        logger.info(f"👤 Creating new user from Clerk: {clerk_user_id}")
        
        # TODO: Verificar si hay una invitación pendiente para este email
        # Por ahora, crear nuevo tenant para cada usuario (su propia organización)
        user_email_prefix = email.split('@')[0].lower().replace('.', '-').replace('_', '-')
        tenant_name = f"org-{user_email_prefix}-{uuid4().hex[:8]}"
        
        logger.info(f"🏢 Creating new organization for user: {tenant_name}")
        user_tenant = AuthService.create_tenant(
            db=db,
            name=tenant_name,
            description=f"Organization for {full_name or email}"
        )
        
        # Crear usuario con password temporal (no se usará con Clerk)
        # Establecer trial de 30 días
        from datetime import datetime, timedelta
        trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        new_user = User(
            id=uuid4(),
            email=email,
            hashed_password=AuthService.get_password_hash("temp_password_from_clerk"),
            full_name=full_name,
            is_superuser=False,
            tenant_id=user_tenant.id,
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
        
        # Subscription data is now handled by Stripe webhooks
        # No need to process it here
        
        logger.info(f"✅ New user created: {new_user.id}")
        return new_user

