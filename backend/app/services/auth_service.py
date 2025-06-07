# backend/app/services/auth_service.py
from datetime import datetime, timedelta
from typing import Optional, Union, Any
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
# Removido jose - usando clerk-backend-api para JWT
from passlib.context import CryptContext
from sqlalchemy.orm import Session
# requests y json removidos - no se usan

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User, Tenant
# TokenPayload removido - ya no se usa JWT interno

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Custom OAuth2 scheme that handles OPTIONS requests
class CustomOAuth2PasswordBearer(OAuth2PasswordBearer):
    async def __call__(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"🔐 [OAUTH2_SCHEME] Called for {request.method} {request.url.path}")
        
        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            logger.info("🔄 [OAUTH2_SCHEME] Skipping OPTIONS request")
            return None
            
        logger.info("🔍 [OAUTH2_SCHEME] Extracting token from Authorization header")
        
        try:
            token = await super().__call__(request)
            logger.info(f"🔑 [OAUTH2_SCHEME] Token extracted successfully: {len(token) if token else 0} chars")
            if token:
                logger.info(f"🔑 [OAUTH2_SCHEME] Token prefix: {token[:30]}...")
            return token
        except Exception as e:
            logger.error(f"❌ [OAUTH2_SCHEME] Error extracting token: {str(e)}")
            logger.error(f"🐛 [OAUTH2_SCHEME] Exception type: {type(e)}")
            raise

oauth2_scheme = CustomOAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login/access-token"
)


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
        # Generar bucket name único
        bucket_name = f"tenant-{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}"
        
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
        """Verifica un token de Clerk usando la API oficial de Clerk."""
        import logging
        import httpx
        from clerk_backend_api import Clerk
        from clerk_backend_api.jwks_helpers import AuthenticateRequestOptions
        
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
            
            # Inicializar cliente de Clerk y verificar token
            logger.info("🏗️ [VERIFY_CLERK_TOKEN] Initializing Clerk client...")
            clerk = Clerk(bearer_auth=settings.CLERK_SECRET_KEY)
            
            logger.info("📨 [VERIFY_CLERK_TOKEN] Creating mock request...")
            mock_request = httpx.Request(
                method="GET",
                url="http://localhost:8000",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            logger.info("⚙️ [VERIFY_CLERK_TOKEN] Setting up auth options...")
            auth_options = AuthenticateRequestOptions(
                authorized_parties=[settings.SERVER_HOST, "http://localhost:3000", "http://localhost:8000"]
            )
            
            logger.info("🔎 [VERIFY_CLERK_TOKEN] Calling Clerk authenticate_request...")
            request_state = clerk.authenticate_request(mock_request, auth_options)
            logger.info(f"📨 [VERIFY_CLERK_TOKEN] Clerk API responded with: {type(request_state)}")
            
            logger.info(f"🔍 [VERIFY_CLERK_TOKEN] Checking request_state: {request_state}")
            logger.info(f"🔍 [VERIFY_CLERK_TOKEN] has is_signed_in: {hasattr(request_state, 'is_signed_in') if request_state else False}")
            logger.info(f"🔍 [VERIFY_CLERK_TOKEN] is_signed_in value: {getattr(request_state, 'is_signed_in', None) if request_state else None}")
            
            if request_state and hasattr(request_state, 'is_signed_in') and request_state.is_signed_in:
                user_id = getattr(request_state, 'user_id', None)
                session_id = getattr(request_state, 'session_id', None)
                
                logger.info(f"🔍 [VERIFY_CLERK_TOKEN] Extracted user_id: {user_id}")
                logger.info(f"🔍 [VERIFY_CLERK_TOKEN] Extracted session_id: {session_id}")
                
                if user_id:
                    logger.info(f"✅ [VERIFY_CLERK_TOKEN] Token verified for user: {user_id}")
                    return {
                        'sub': user_id,
                        'session_id': session_id,
                        'iss': 'clerk'
                    }
                else:
                    logger.error("❌ [VERIFY_CLERK_TOKEN] No user_id in token")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="No user ID in token",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            else:
                logger.error("❌ [VERIFY_CLERK_TOKEN] Invalid or expired token")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
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
    def get_current_user(
        db: Session = Depends(get_db),
        token: str = Depends(oauth2_scheme)
    ) -> User:
        """Obtiene el usuario actual basado en el token JWT o Clerk token."""
        import logging
        logger = logging.getLogger(__name__)
        
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            logger.info(f"🚀 [AUTH_SERVICE] Starting authentication...")
            
            logger.info(f"📞 [AUTH_SERVICE] Calling verify_clerk_token")
            clerk_payload = AuthService.verify_clerk_token(token)
            clerk_user_id = clerk_payload.get('sub')
            logger.info(f"✅ [AUTH_SERVICE] verify_clerk_token returned user_id: {clerk_user_id}")
            
            if clerk_user_id:
                user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
                if user:
                    logger.info(f"✅ User authenticated: {user.email}")
                    return user
                else:
                    logger.warning(f"⚠️ User not found for Clerk ID: {clerk_user_id}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found. Please sync your account first.",
                    )
            else:
                raise credentials_exception
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Auth Error: {str(e)}")
            raise credentials_exception

    @staticmethod
    def get_current_active_user(
        current_user: User = Depends(get_current_user)
    ) -> User:
        """Obtiene el usuario actual si está activo."""
        if not current_user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user

    @staticmethod
    def sync_user_from_clerk(
        db: Session,
        clerk_user_id: str,
        email: str,
        full_name: str
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
            db.commit()
            db.refresh(user_by_email)
            return user_by_email
        
        # Usuario no existe, crear uno nuevo
        logger.info(f"👤 Creating new user from Clerk: {clerk_user_id}")
        
        # Obtener tenant por defecto
        default_tenant = db.query(Tenant).filter(
            Tenant.name == settings.DEFAULT_TENANT
        ).first()
        
        if not default_tenant:
            # Crear tenant por defecto si no existe
            logger.info("🏢 Creating default tenant")
            default_tenant = AuthService.create_tenant(
                db=db,
                name=settings.DEFAULT_TENANT,
                description="Default tenant for new users"
            )
        
        # Crear usuario con password temporal (no se usará con Clerk)
        new_user = User(
            id=uuid4(),
            email=email,
            hashed_password=AuthService.get_password_hash("temp_password_from_clerk"),
            full_name=full_name,
            is_superuser=False,
            tenant_id=default_tenant.id,
            clerk_user_id=clerk_user_id,
            is_active=True
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"✅ New user created: {new_user.id}")
        return new_user