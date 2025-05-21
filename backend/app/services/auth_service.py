import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import verify_password, get_password_hash
from app.db.database import get_db
from app.db.models import User, Tenant
from app.schemas.auth import TokenPayload

logger = logging.getLogger(__name__)

# Esquema de autenticación OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")

# Constantes para JWT
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


class AuthService:
    """Servicio para gestión de autenticación y autorización"""
    
    @staticmethod
    def create_access_token(subject: str, tenant_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """
        Crea un token JWT de acceso.
        
        Args:
            subject: Identificador del usuario (ID)
            tenant_id: ID del tenant
            expires_delta: Tiempo de expiración opcional
            
        Returns:
            Token JWT codificado
        """
        if expires_delta:
            expire = datetime.now() + expires_delta
        else:
            expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {
            "exp": expire, 
            "iat": datetime.now(),  # Añadir tiempo de emisión
            "sub": subject,
            "tid": tenant_id
        }
        
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """
        Autentica un usuario verificando sus credenciales.
        
        Args:
            db: Sesión de base de datos
            email: Email del usuario
            password: Contraseña en texto plano
            
        Returns:
            Usuario autenticado o None si falla la autenticación
        """
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    @staticmethod
    def get_current_user(
        db: Session = Depends(get_db),
        token: str = Depends(oauth2_scheme)
    ) -> User:
        """
        Obtiene el usuario actual a partir del token JWT.
        
        Args:
            db: Sesión de base de datos
            token: Token JWT de autenticación
            
        Returns:
            Usuario autenticado
            
        Raises:
            HTTPException: Si el token es inválido o el usuario no existe
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_data = TokenPayload(**payload)
            
            # Verificar que el token no haya expirado
            if datetime.fromtimestamp(token_data.exp) < datetime.now():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )
                
        except (JWTError, ValidationError):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user = db.query(User).filter(User.id == token_data.sub).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
            
        # Verificar que el tenant coincida
        if str(user.tenant_id) != token_data.tid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch in token",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return user
    
    @staticmethod
    def get_current_active_superuser(
        current_user: User = Depends(get_current_user),
    ) -> User:
        """
        Verifica que el usuario actual sea superusuario.
        
        Args:
            current_user: Usuario actual
            
        Returns:
            Usuario superusuario
            
        Raises:
            HTTPException: Si el usuario no es superusuario
        """
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
        is_superuser: bool = False,
        tenant_id: Optional[str] = None
    ) -> User:
        """
        Crea un nuevo usuario.
        
        Args:
            db: Sesión de base de datos
            email: Email del usuario
            password: Contraseña en texto plano
            full_name: Nombre completo (opcional)
            is_superuser: Si el usuario es superusuario
            tenant_id: ID del tenant (opcional, usa el default si no se proporciona)
            
        Returns:
            Usuario creado
            
        Raises:
            HTTPException: Si el email ya está en uso
        """
        # Verificar si el email ya existe
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Usar tenant_id proporcionado o el default
        tenant_id = tenant_id or settings.DEFAULT_TENANT
        
        # Verificar si el tenant existe
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            # Usar el tenant default si existe
            tenant = db.query(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT).first()
            
            if not tenant:
                # Crear tenant default si no existe
                tenant = Tenant(
                    id=uuid.uuid4(),
                    name=settings.DEFAULT_TENANT,
                    description="Default tenant",
                    bucket_name=f"{settings.GCS_BUCKET_NAME}-{settings.DEFAULT_TENANT}"
                )
                db.add(tenant)
                db.flush()
        
        # Crear usuario
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            is_superuser=is_superuser,
            tenant_id=tenant.id
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return user

    @classmethod
    def create_tenant(
        cls,
        db: Session,
        name: str,
        description: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> Tenant:
        """
        Crea un nuevo tenant.
        
        Args:
            db: Sesión de base de datos
            name: Nombre del tenant
            description: Descripción del tenant
            settings: Configuraciones adicionales
            
        Returns:
            Tenant creado
            
        Raises:
            HTTPException: Si el nombre ya está en uso
        """
        # Verificar si el nombre ya existe
        existing_tenant = db.query(Tenant).filter(Tenant.name == name).first()
        if existing_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant name already exists"
            )
        
        # Crear tenant
        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            description=description or "",
            bucket_name=f"{settings.GCS_BUCKET_NAME}-{name.lower()}",
            settings=settings
        )
        
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        
        return tenant