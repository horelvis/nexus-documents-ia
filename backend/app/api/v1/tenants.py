from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.dependencies import get_current_active_superuser, get_current_user
from app.db.database import get_db
from app.db.models import User, Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantWithUsers
from app.services.auth_service import AuthService

router = APIRouter()


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Lista todos los tenants (solo administradores).
    """
    tenants = db.query(Tenant).offset(skip).limit(limit).all()
    return tenants


@router.post("/", response_model=TenantResponse)
async def create_tenant(
    tenant_in: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Crea un nuevo tenant (solo administradores).
    """
    # Verificar si ya existe un tenant con ese nombre
    db_tenant = db.query(Tenant).filter(Tenant.name == tenant_in.name).first()
    if db_tenant:
        raise HTTPException(
            status_code=400,
            detail="El nombre de tenant ya existe"
        )
    
    # Crear tenant
    tenant = AuthService.create_tenant(
        db=db,
        name=tenant_in.name,
        description=tenant_in.description,
        settings=tenant_in.settings
    )
    
    return tenant


@router.get("/{tenant_id}", response_model=TenantWithUsers)
async def get_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Obtiene información detallada de un tenant (solo administradores).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    return tenant


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    tenant_in: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Actualiza un tenant existente (solo administradores).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    # Verificar nombre duplicado si se está cambiando
    if tenant_in.name and tenant_in.name != tenant.name:
        db_tenant = db.query(Tenant).filter(Tenant.name == tenant_in.name).first()
        if db_tenant:
            raise HTTPException(
                status_code=400,
                detail="El nombre de tenant ya existe"
            )
    
    # Actualizar campos
    update_data = tenant_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)
    
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    
    return tenant


@router.delete("/{tenant_id}", response_model=dict)
async def delete_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Elimina un tenant (solo administradores).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    # Verificar que no sea el tenant default
    from app.core.config import settings
    if tenant.name == settings.DEFAULT_TENANT:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar el tenant default"
        )
    
    # Verificar si tiene usuarios asociados
    if tenant.users:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un tenant con usuarios asociados"
        )
    
    # Eliminar tenant
    db.delete(tenant)
    db.commit()
    
    return {"message": f"Tenant {tenant_id} eliminado exitosamente"}


@router.get("/current", response_model=TenantResponse)
async def get_current_tenant(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene información del tenant actual del usuario.
    """
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    return tenant