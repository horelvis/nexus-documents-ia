# backend/app/services/auth_service.py
from datetime import datetime, timedelta
from typing import Optional, Union, Any, Dict
from uuid import uuid4
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import requests
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User, Tenant
from app.schemas.auth import TokenPayload

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login/access-token"
)

# Cache para las claves JWKS de Clerk
_jwks_cache: Dict[str, Any] = {}
_jwks_cache_expiry: float = 0
JWKS_CACHE_TTL = 3600  # 1 hora

class AuthService:
    @staticmethod
    def _get_clerk_jwks() -> Dict[str, Any]:
        """Obtiene las claves JWKS de Clerk con cache."""
        global _jwks_cache, _jwks_cache_expiry
        
        current_time = time.time()
        
        # Verificar si el cache es válido
        if current_time < _jwks_cache_expiry and _jwks_cache:
            return _jwks_cache
        
        # Obtener nuevas claves de Clerk
        try:
            jwks_url = "https://api.clerk.dev/v1/jwks"
            response = requests.get(jwks_url, timeout=10)
            response.raise_for_status()
            jwks = response.json()
            
            # Actualizar cache
            _jwks_cache = jwks
            _jwks_cache_expiry = current_time + JWKS_CACHE_TTL
            
            return jwks
            
        except requests.RequestException as e:
            # Si falla la petición pero tenemos cache, usarlo
            if _jwks_cache:
                return _jwks_cache
            raise e
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica que la contraseña coincida con el hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Genera un hash de la contraseña."""
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(
        subject: Union[str, Any], 
        tenant_id: str,
        expires_delta: timedelta = None
    ) -> str:
        """Crea un token de acceso JWT."""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        
        to_encode = {
            "exp": expire,
            "sub": str(subject),
            "tid": tenant_id
        }
        
        encoded_jwt = jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )
        return encoded_jwt

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
        """Verifica un token de Clerk usando las claves públicas oficiales."""
        import logging
        import jwcrypto.jwk as jwk
        import jwcrypto.jwt as jwcrypto_jwt
        from jwcrypto.common import json_encode, json_decode
        
        logger = logging.getLogger(__name__)
        
        try:
            # Verificar que tenemos las credenciales de Clerk configuradas
            if not settings.CLERK_SECRET_KEY:
                logger.error("❌ CLERK_SECRET_KEY not configured")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Clerk authentication not properly configured"
                )
            
            # Obtener las claves públicas de Clerk para verificar el token
            try:
                # Extraer el header del JWT para obtener el kid (key ID)
                header = jwt.get_unverified_header(token)
                kid = header.get('kid')
                
                if not kid:
                    raise ValueError("Token missing 'kid' in header")
                
                # Obtener las claves públicas de Clerk (con cache)
                jwks = AuthService._get_clerk_jwks()
                
                # Buscar la clave correcta usando el kid
                key_data = None
                for key in jwks.get('keys', []):
                    if key.get('kid') == kid:
                        key_data = key
                        break
                
                if not key_data:
                    raise ValueError(f"Key with kid '{kid}' not found in JWKS")
                
                # Crear el objeto de clave pública para verificación
                public_key = jwk.JWK(**key_data)
                
                # Verificar el token
                jwt_token = jwcrypto_jwt.JWT(jwt=token, key=public_key)
                payload = json_decode(jwt_token.claims)
                
                # Verificaciones adicionales
                if not payload.get('sub'):
                    raise ValueError("Token missing 'sub' claim")
                
                # Verificar el issuer
                iss = payload.get('iss', '')
                if not iss or 'clerk' not in iss:
                    raise ValueError(f"Invalid issuer: {iss}")
                
                logger.info(f"🔑 Clerk token verified successfully: {payload.get('sub')}")
                return payload
                
            except requests.RequestException as e:
                logger.error(f"❌ Failed to fetch Clerk JWKS: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to verify token - Clerk service unavailable"
                )
            
        except ValueError as e:
            logger.error(f"❌ Token validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"❌ Unexpected error verifying Clerk token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
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
            # Intentar verificar como token de Clerk primero
            try:
                clerk_payload = AuthService.verify_clerk_token(token)
                clerk_user_id = clerk_payload.get('sub')
                
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
                logger.info("🔄 Trying internal JWT verification...")
                try:
                    payload = jwt.decode(
                        token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                    )
                    token_data = TokenPayload(**payload)
                    
                    user = db.query(User).filter(User.id == token_data.sub).first()
                    if user is None:
                        raise credentials_exception
                    
                    return user
                except JWTError as jwt_error:
                    logger.error(f"❌ JWT Error: {str(jwt_error)}")
                    raise credentials_exception
                
        except JWTError as e:
            logger.error(f"❌ JWT Error: {str(e)}")
            raise credentials_exception
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