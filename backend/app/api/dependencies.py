from typing import Generator, Optional

from fastapi import Depends, HTTPException, status, Header

from app.db.database import get_db
from app.db.models import User
from app.services.auth_service import AuthService, oauth2_scheme
from app.core.config import settings


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Obtiene el usuario actual autenticado.
    """
    return AuthService.get_current_user(db=db, token=token)


def get_current_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None)
) -> str:
    """
    Obtiene el ID del tenant actual.
    
    Si el encabezado X-Tenant-ID está presente y es válido, lo usa.
    De lo contrario, usa el tenant del usuario actual.
    """
    # En modo multi-tenant, permiso para override solo para superusuarios
    if settings.MULTI_TENANT and x_tenant_id and current_user.is_superuser:
        return x_tenant_id
    
    # Usar tenant del usuario por defecto
    return str(current_user.tenant_id)


def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Verifica que el usuario actual tenga permisos de administrador.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user