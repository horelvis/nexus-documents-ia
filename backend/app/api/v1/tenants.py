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
from sqlalchemy import select, func
from app.db.models import Document
import logging

logger = logging.getLogger(__name__)
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


@router.get("/stats", response_model=dict)
async def get_tenant_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async)
):
    """
    Obtiene estadísticas del tenant actual.
    """
    tenant_id = str(current_user.tenant_id)
    
    # Count users in tenant
    stmt = select(func.count(User.id)).filter(
        User.tenant_id == current_user.tenant_id,
        User.is_active == True
    )
    result = await db.execute(stmt)
    total_users = result.scalar() or 0
    
    # Count documents in tenant
    stmt = select(func.count(Document.id)).filter(
        Document.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    total_documents = result.scalar() or 0
    
    # Calculate storage used
    stmt = select(func.sum(Document.file_size)).filter(
        Document.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    storage_used_bytes = result.scalar() or 0
    
    # Get tenant limits from tenant settings
    stmt = select(Tenant).filter(Tenant.id == current_user.tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    # Get limits from tenant settings or use defaults
    settings = tenant.settings if tenant and tenant.settings else {}
    storage_limit_bytes = settings.get('max_storage_bytes', 10 * 1024 * 1024 * 1024)  # 10GB default
    
    # Count documents by type
    stmt = select(
        Document.file_type, 
        func.count(Document.id)
    ).filter(
        Document.tenant_id == tenant_id
    ).group_by(Document.file_type)
    result = await db.execute(stmt)
    doc_types = result.all()
    
    documents_by_type = {
        file_type: count for file_type, count in doc_types
    }
    
    # Count documents by status
    stmt = select(
        Document.indexed, 
        func.count(Document.id)
    ).filter(
        Document.tenant_id == tenant_id
    ).group_by(Document.indexed)
    result = await db.execute(stmt)
    doc_statuses = result.all()
    
    documents_by_status = {}
    for status, count in doc_statuses:
        if status == 0:
            documents_by_status['pending'] = count
        elif status == 1:
            documents_by_status['indexed'] = count
        elif status == 2:
            documents_by_status['error'] = count
    
    return {
        "total_documents": total_documents,
        "total_users": total_users,
        "storage_used_bytes": storage_used_bytes,
        "storage_limit_bytes": storage_limit_bytes,
        "documents_by_type": documents_by_type,
        "documents_by_status": documents_by_status
    }


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


@router.get("/validate/{tenant_id}")
async def validate_tenant_exists(
    tenant_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Valida si un tenant existe (endpoint público para middleware).
    Retorna solo información básica sin datos sensibles.
    """
    try:
        # Convertir string a UUID
        from uuid import UUID
        tenant_uuid = UUID(tenant_id)

        result = await db.execute(
            select(Tenant.id, Tenant.name, Tenant.is_active)
            .where(Tenant.id == tenant_uuid)
        )
        tenant = result.first()

        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        if not tenant.is_active:
            raise HTTPException(status_code=404, detail="Tenant inactivo")

        # Retornar solo información básica
        return {
            "id": str(tenant.id),
            "name": tenant.name,
            "is_active": tenant.is_active
        }

    except ValueError:
        # Invalid UUID format
        raise HTTPException(status_code=404, detail="Formato de tenant ID inválido")
    except Exception as e:
        logger.error(f"Error validating tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
