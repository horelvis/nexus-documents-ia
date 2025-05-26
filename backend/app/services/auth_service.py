from doctest import DebugRunner
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid

from fastapi import Depends, HTTPException, status # Depends might be removed if not used for Prisma client
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError # Keep for TokenPayload validation
from prisma import Prisma # Import Prisma client

from app.core.config import settings
from app.core.security import verify_password, get_password_hash
# Remove SQLAlchemy specific imports if no longer used directly here
# from app.db.database import get_db 
# from app.db.models import User, Tenant # These are SQLAlchemy models
from app.db.repositories import users as user_repo
from app.db.repositories import tenants as tenant_repo
from app.schemas.auth import TokenPayload # Pydantic schema for token
# Assuming Prisma models will be aliased or handled by repository return types
# from prisma.models import User as PrismaUser, Tenant as PrismaTenant


logger = logging.getLogger(__name__)

# Esquema de autenticación OAuth2 - Remains the same
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")

# Constantes para JWT - Remains the same
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


# Dependency to get Prisma client (example, can be improved with lifespan events)
# This is a placeholder. A robust solution would use FastAPI's lifespan events
# to connect/disconnect and a dependency to provide the client instance.
async def get_prisma_db() -> Prisma:
    db = Prisma()
    await db.connect()
    try:
        yield db
    finally:
        if db.is_connected():
            await db.disconnect()

class AuthService:
    """Servicio para gestión de autenticación y autorización"""
    
    @staticmethod
    def create_access_token(subject: str, tenant_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """
        Crea un token JWT de acceso. (Logic remains the same)
        """
        if expires_delta:
            expire = datetime.now() + expires_delta
        else:
            expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {
            "exp": expire, 
            "iat": datetime.now(),
            "sub": subject,
            "tid": tenant_id
        }
        
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    async def authenticate_user(db: Prisma, email: str, password: str) -> Optional[user_repo.PrismaUser]:
        """
        Autentica un usuario verificando sus credenciales con Prisma.
        """
        user = await user_repo.get_user_by_email(db, email=email)
        if not user:
            return None
        # hashedPassword might be null if user created via social OAuth and password not set
        if not user.hashedPassword or not verify_password(password, user.hashedPassword):
            return None
        return user
    
    @staticmethod
    async def get_current_user(
        # db: Prisma = Depends(get_prisma_db), # Use your Prisma dependency
        db: Prisma, # For now, assume db is passed directly or managed by endpoint
        token: str = Depends(oauth2_scheme)
    ) -> user_repo.PrismaUser:
        """
        Obtiene el usuario actual a partir del token JWT usando Prisma.
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_data = TokenPayload(**payload)
            
            if datetime.fromtimestamp(token_data.exp) < datetime.now():
                raise credentials_exception # Re-use for token expired
                
        except (JWTError, ValidationError):
            raise credentials_exception
        
        # user_id from token_data.sub should be a string already if Prisma IDs are strings
        user = await user_repo.get_user(db, user_id=token_data.sub)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
            
        if not user.isActive: # Prisma model uses isActive
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user"
            )
            
        if str(user.tenantId) != token_data.tid: # Prisma model uses tenantId
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch in token",
            )
            
        return user
    
    @staticmethod
    async def get_current_active_superuser( # Signature changes to async
        current_user: user_repo.PrismaUser = Depends(AuthService.get_current_user), # Depends on the async version
    ) -> user_repo.PrismaUser:
        """
        Verifica que el usuario actual sea superusuario.
        """
        # get_current_user is now async, so this function must be async too if it Depends on it.
        # However, FastAPI Doesn't support async dependencies directly in Depends like this for methods.
        # This part needs careful handling of async dependencies in FastAPI.
        # For this refactor, we assume current_user is passed correctly.
        # If get_current_user is a path operation dependency, it will be resolved.

        if not current_user.isSuperuser: # Prisma model uses isSuperuser
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The user doesn't have enough privileges"
            )
        return current_user
    
    @classmethod
    async def create_user(
        cls,
        db: Prisma,
        email: str,
        password: str,
        tenant_id: str, # Assuming tenant_id is a string (UUID)
        is_superuser: bool = False,
        full_name: Optional[str] = None,
        clerk_user_id: Optional[str] = None # Added clerkUserId
    ) -> user_repo.PrismaUser:
        """
        Crea un nuevo usuario con Prisma.
        """
        existing_user = await user_repo.get_user_by_email(db, email=email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Ensure tenant exists
        tenant = await tenant_repo.get_tenant(db, tenant_id=tenant_id)
        if not tenant:
            # As per original logic, it seems tenant creation was implicit if ID was given but not found.
            # This is risky. It's better to ensure tenant exists or handle tenant creation explicitly.
            # For now, let's assume tenant_id must be valid and tenant must exist.
            # If auto-creation is desired, it should call tenant_repo.create_tenant.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with ID {tenant_id} not found."
            )
        
        user_data = {
            "email": email,
            "hashedPassword": get_password_hash(password),
            "fullName": full_name,
            "isSuperuser": is_superuser,
            "isActive": True, # Default to active
            "tenantId": tenant.id, # Use the validated tenant's ID
            "clerkUserId": clerk_user_id
        }
        
        new_user = await user_repo.create_user(db, user_data=user_data)
        return new_user

    @classmethod
    async def create_tenant(
        cls,
        db: Prisma,
        name: str,
        description: Optional[str] = None,
        # settings: Optional[Dict[str, Any]] = None # Prisma schema doesn't have settings on Tenant yet
    ) -> tenant_repo.PrismaTenant:
        """
        Crea un nuevo tenant con Prisma.
        """
        existing_tenant = await tenant_repo.get_tenant_by_name(db, name=name)
        if existing_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant name already exists"
            )
        
        tenant_data = {
            "name": name,
            "description": description,
            "isActive": True # Default to active
            # bucket_name and settings were omitted in Prisma schema for simplicity, add if needed
        }
        
        new_tenant = await tenant_repo.create_tenant(db, tenant_data=tenant_data)
        return new_tenant