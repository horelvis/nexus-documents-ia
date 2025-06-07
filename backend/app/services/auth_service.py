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

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(
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
            logger.info(f"🔍 [CLERK_VERIFY] Starting Clerk token verification...")
            logger.info(f"📝 [CLERK_VERIFY] Token length: {len(token) if token else 0}")
            logger.info(f"📝 [CLERK_VERIFY] Token preview: {token[:30]}..." if token and len(token) > 30 else f"📝 [CLERK_VERIFY] Full token: {token}")
            logger.info(f"🔐 [CLERK_VERIFY] Clerk secret key configured: {'Yes' if settings.CLERK_SECRET_KEY else 'No'}")
            logger.info(f"🔐 [CLERK_VERIFY] Clerk secret preview: {'***' + settings.CLERK_SECRET_KEY[-10:] if settings.CLERK_SECRET_KEY and len(settings.CLERK_SECRET_KEY) > 10 else 'Not set'}")
            logger.info(f"🌐 [CLERK_VERIFY] Server host: {settings.SERVER_HOST}")
            
            if not settings.CLERK_SECRET_KEY:
                logger.error("❌ [CLERK_VERIFY] CLERK_SECRET_KEY not configured")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Clerk not properly configured",
                )
            
            if not token:
                logger.error("❌ [CLERK_VERIFY] No token provided")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No token provided",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                
            if not token.startswith("clerk_"):
                logger.warning(f"⚠️ [CLERK_VERIFY] Token doesn't start with 'clerk_' - may be invalid format")
                logger.warning(f"🔍 [CLERK_VERIFY] Token starts with: {token[:10]}")
            
            # Check token format
            token_parts = token.split("_")
            logger.info(f"🔍 [CLERK_VERIFY] Token parts count: {len(token_parts)}")
            if len(token_parts) >= 2:
                logger.info(f"🔍 [CLERK_VERIFY] Token type: {token_parts[0]}")
                logger.info(f"🔍 [CLERK_VERIFY] Token identifier: {token_parts[1][:10]}..." if len(token_parts[1]) > 10 else f"🔍 [CLERK_VERIFY] Token identifier: {token_parts[1]}")
            else:
                logger.warning(f"⚠️ [CLERK_VERIFY] Token format seems invalid - expected clerk_xxx format")
            
            # Inicializar cliente de Clerk
            logger.info(f"🏗️ [CLERK_VERIFY] Initializing Clerk client...")
            try:
                clerk = Clerk(bearer_auth=settings.CLERK_SECRET_KEY)
                logger.info(f"✅ [CLERK_VERIFY] Clerk client initialized successfully")
            except Exception as client_error:
                logger.error(f"❌ [CLERK_VERIFY] Failed to initialize Clerk client: {str(client_error)}")
                raise
            
            # Crear un request mock para usar con authenticate_request
            logger.info(f"🔧 [CLERK_VERIFY] Creating mock request with Bearer token...")
            mock_url = "http://localhost:8000"
            logger.info(f"🔧 [CLERK_VERIFY] Mock URL: {mock_url}")
            logger.info(f"🔧 [CLERK_VERIFY] Authorization header: Bearer {token[:20]}..." if len(token) > 20 else f"🔧 [CLERK_VERIFY] Authorization header: Bearer {token}")
            
            try:
                mock_request = httpx.Request(
                    method="GET",
                    url=mock_url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                logger.info(f"📨 [CLERK_VERIFY] Mock request created successfully")
                logger.info(f"📨 [CLERK_VERIFY] Mock request headers: {dict(mock_request.headers)}")
            except Exception as request_error:
                logger.error(f"❌ [CLERK_VERIFY] Failed to create mock request: {str(request_error)}")
                raise
            
            # Configurar opciones de autenticación
            logger.info(f"⚙️ [CLERK_VERIFY] Setting up authentication options...")
            authorized_parties = [settings.SERVER_HOST, "http://localhost:3000", "http://localhost:8000"]
            logger.info(f"🌐 [CLERK_VERIFY] Authorized parties: {authorized_parties}")
            
            try:
                auth_options = AuthenticateRequestOptions(
                    authorized_parties=authorized_parties
                )
                logger.info(f"✅ [CLERK_VERIFY] Auth options configured")
            except Exception as options_error:
                logger.error(f"❌ [CLERK_VERIFY] Failed to create auth options: {str(options_error)}")
                raise
            
            # Verificar el token usando authenticate_request
            logger.info(f"🔎 [CLERK_VERIFY] Calling Clerk authenticate_request...")
            try:
                request_state = clerk.authenticate_request(mock_request, auth_options)
                logger.info(f"📨 [CLERK_VERIFY] Clerk API response received: {type(request_state)}")
                logger.info(f"📨 [CLERK_VERIFY] Request state object: {request_state}")
            except Exception as auth_error:
                logger.error(f"❌ [CLERK_VERIFY] Clerk authenticate_request failed: {str(auth_error)}")
                logger.error(f"🐛 [CLERK_VERIFY] Auth error type: {type(auth_error)}")
                raise
            
            if request_state:
                logger.info(f"📊 Request state attributes: {dir(request_state)}")
                logger.info(f"🔓 Is signed in: {getattr(request_state, 'is_signed_in', 'N/A')}")
                
                if hasattr(request_state, 'is_signed_in') and request_state.is_signed_in:
                    logger.info(f"✅ User is signed in")
                    
                    # Obtener información del usuario
                    user_id = getattr(request_state, 'user_id', None)
                    session_id = getattr(request_state, 'session_id', None)
                    
                    logger.info(f"👤 User ID: {user_id}")
                    logger.info(f"🎫 Session ID: {session_id}")
                    
                    if user_id:
                        # Crear payload compatible con nuestro sistema
                        payload = {
                            'sub': user_id,
                            'session_id': session_id,
                            'iss': 'clerk'
                        }
                        logger.info(f"🔑 Clerk token verified successfully")
                        return payload
                    else:
                        logger.error(f"❌ No user_id found in request state")
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="No user ID in token",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                else:
                    logger.error(f"❌ User is not signed in")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not signed in",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            else:
                logger.error("❌ Clerk API returned None/empty result")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                
        except HTTPException as he:
            # Re-raise HTTP exceptions with additional logging
            logger.error(f"🔄 [CLERK_VERIFY] Re-raising HTTP exception: {he.status_code} - {he.detail}")
            logger.error(f"📋 [CLERK_VERIFY] HTTP exception headers: {he.headers}")
            raise
        except Exception as e:
            logger.error(f"❌ [CLERK_VERIFY] Unexpected error verifying Clerk token: {str(e)}")
            logger.error(f"🐛 [CLERK_VERIFY] Exception type: {type(e)}")
            logger.error(f"📜 [CLERK_VERIFY] Exception args: {e.args}")
            logger.error(f"🔧 [CLERK_VERIFY] Token that failed: {token[:10]}...{token[-10:] if len(token) > 20 else ''}")
            logger.error(f"⚙️ [CLERK_VERIFY] Clerk secret configured: {'Yes' if settings.CLERK_SECRET_KEY else 'No'}")
            logger.error(f"🌐 [CLERK_VERIFY] Authorized parties: {auth_options.authorized_parties if 'auth_options' in locals() else 'Not set'}")
            
            # Log more specific error types
            if "Unauthorized" in str(e) or "401" in str(e):
                logger.error(f"🚫 [CLERK_VERIFY] Authorization error - token may be invalid or expired")
            elif "Network" in str(e) or "Connection" in str(e):
                logger.error(f"🌐 [CLERK_VERIFY] Network error - can't reach Clerk API")
            elif "Key" in str(e) or "Secret" in str(e):
                logger.error(f"🔑 [CLERK_VERIFY] Key error - check Clerk configuration")
            
            import traceback
            logger.error(f"📚 [CLERK_VERIFY] Full traceback: {traceback.format_exc()}")
            
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
            logger.info(f"🚀 Starting user authentication process...")
            logger.info(f"🔑 Token preview: {token[:20]}..." if token else "❌ No token provided")
            
            # Intentar verificar como token de Clerk primero
            try:
                logger.info(f"🔍 Attempting Clerk token verification...")
                clerk_payload = AuthService.verify_clerk_token(token)
                logger.info(f"✅ Clerk verification successful")
                clerk_user_id = clerk_payload.get('sub')
                logger.info(f"👤 Clerk user ID extracted: {clerk_user_id}")
                
                if clerk_user_id:
                    # Buscar usuario por clerk_user_id
                    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
                    if user:
                        logger.info(f"✅ User found by Clerk ID: {user.id}")
                        return user
                    else:
                        logger.warning(f"⚠️ User not found for Clerk ID: {clerk_user_id}")
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found. Please sync your account first.",
                        )
            except HTTPException:
                # Re-raise HTTP exceptions from Clerk verification
                raise
            except Exception as e:
                # Si falla la verificación de Clerk, intentar como JWT interno
                logger.warning(f"⚠️ Clerk verification failed: {str(e)}")
                logger.info("🔄 Trying internal JWT verification...")
                # JWT interno ya no se usa - solo Clerk
                logger.error("❌ Internal JWT not supported - use Clerk authentication")
                raise credentials_exception
                
        # JWTError ya no se usa
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