from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.api.async_dependencies import get_current_active_superuser_async, get_current_user_async
from app.db.async_database import get_async_db
from app.db.models import User, Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantWithUsers
from app.services.async_auth_service import AsyncAuthService

router = APIRouter()


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Lista todos los tenants (solo administradores).
    """
    result = await db.execute(
        select(Tenant).offset(skip).limit(limit)
    )
    tenants = result.scalars().all()
    return tenants


@router.post("/", response_model=TenantResponse)
async def create_tenant(
    tenant_in: TenantCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Crea un nuevo tenant (solo administradores).
    """
    # Verificar si ya existe un tenant con ese nombre
    result = await db.execute(
        select(Tenant).where(Tenant.name == tenant_in.name)
    )
    db_tenant = result.scalar_one_or_none()
    
    if db_tenant:
        raise HTTPException(
            status_code=400,
            detail="El nombre de tenant ya existe"
        )
    
    # Crear tenant
    tenant = await AsyncAuthService.create_tenant(
        db=db,
        name=tenant_in.name,
        description=tenant_in.description,
        settings=tenant_in.settings
    )
    
    return tenant


@router.get("/{tenant_id}", response_model=TenantWithUsers)
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Obtiene información detallada de un tenant (solo administradores).
    """
    result = await db.execute(
        select(Tenant)
        .options(selectinload(Tenant.users))
        .where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    return tenant


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    tenant_in: TenantUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Actualiza un tenant existente (solo administradores).
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    # Verificar nombre duplicado si se está cambiando
    if tenant_in.name and tenant_in.name != tenant.name:
        result = await db.execute(
            select(Tenant).where(Tenant.name == tenant_in.name)
        )
        db_tenant = result.scalar_one_or_none()
        
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
    await db.commit()
    await db.refresh(tenant)
    
    return tenant


@router.delete("/{tenant_id}", response_model=dict)
async def delete_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Elimina un tenant (solo administradores).
    """
    result = await db.execute(
        select(Tenant)
        .options(selectinload(Tenant.users))
        .where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    
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
    await db.delete(tenant)
    await db.commit()
    
    return {"message": f"Tenant {tenant_id} eliminado exitosamente"}


@router.get("/current", response_model=TenantResponse)
async def get_current_tenant(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async)
):
    """
    Obtiene información del tenant actual del usuario.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    
    return tenant