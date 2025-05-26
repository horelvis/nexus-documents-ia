from typing import Generator, Optional

from fastapi import Depends, HTTPException, status, Header

from app.db.database import get_db
from app.db.models import User
from app.services.auth_service import AuthService, oauth2_scheme
from app.core.config import settings
from sqlalchemy.orm import Session # Keep for now if other parts of app still use it
from fastapi.security.api_key import APIKeyHeader
from fastapi import Security

# Import Prisma client from main.py (or where it's initialized)
from app.main import db_client as prisma_client_instance # Renamed to avoid conflict
from prisma import Prisma


# Prisma DB Dependency
async def get_prisma_db() -> Prisma:
    if not prisma_client_instance.is_connected():
        await prisma_client_instance.connect()
    # Note: Connection is managed by lifespan events in main.py for the global instance.
    # This dependency just returns the already connected (or soon to be connected) instance.
    return prisma_client_instance


# API Key Authentication
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key_header_value: Optional[str] = Security(api_key_header)):
    if not api_key_header_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authenticated: X-API-KEY header missing."
        )
    if api_key_header_value != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid API Key."
        )
    return True # API key is valid


# Existing SQLAlchemy-based dependencies (to be phased out or adapted)
def get_current_user( # This will need to be refactored to use Prisma
    db: Session = Depends(get_db), # Still uses SQLAlchemy Session
    token: str = Depends(oauth2_scheme)
) -> User: # Returns SQLAlchemy User model
    """
    Obtiene el usuario actual autenticado. (SQLAlchemy version)
    TODO: Refactor this to use Prisma and AuthService.get_current_user (async)
    """
    # This is the old SQLAlchemy based method.
    # The new AuthService.get_current_user is async and expects Prisma client.
    # This dependency needs to be updated or replaced.
    # For now, keeping it as is, but it won't work with Prisma-based AuthService.
    # return AuthService.get_current_user(db=db, token=token)
    # Placeholder: raise an error or return a mock, as direct call to async from sync is not good.
    raise NotImplementedError("get_current_user dependency needs refactoring for Prisma and async AuthService.")


def get_current_tenant_id( # This also depends on SQLAlchemy User
    current_user: User = Depends(get_current_user), 
    x_tenant_id: Optional[str] = Header(None)
) -> str: # Returns SQLAlchemy User model
    """
    Obtiene el ID del tenant actual.
    
    Si el encabezado X-Tenant-ID está presente y es válido, lo usa.
    De lo contrario, usa el tenant del usuario actual.
    """
    # En modo multi-tenant, permiso para override solo para superusuarios
    # TODO: Refactor current_user to be Prisma User model
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser: # type: ignore
        return x_tenant_id
    
    # Usar tenant del usuario por defecto
    return str(current_user.tenant_id) # type: ignore


def get_current_active_superuser( # Depends on SQLAlchemy User
    current_user: User = Depends(get_current_user),
) -> User: # Returns SQLAlchemy User model
    """
    Verifica que el usuario actual tenga permisos de administrador.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user