from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
import logging

from app.api.async_dependencies import get_current_active_superuser_async
from app.db.async_database import get_async_db
from app.db.models import User, Tenant, Document, DocumentMetrics, DocumentView
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.async_auth_service import AsyncAuthService
from app.services.async_document_service import AsyncDocumentService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    tenant_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Lista todos los usuarios del sistema (solo administradores).
    """
    print(f"DEBUG - Current user: {current_user}")  # Agrega este print para depuración
    
    stmt = select(User)
    if tenant_id:
        stmt = stmt.filter(User.tenant_id == tenant_id)
    stmt = stmt.offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Crea un nuevo usuario (solo administradores).
    """
    # Verificar si el email ya existe
    stmt = select(User).filter(User.email == user_in.email)
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="El email ya está registrado"
        )
    
    # Verificar que el tenant exista
    stmt = select(Tenant).filter(Tenant.id == user_in.tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant no encontrado"
        )
    
    # Crear usuario
    user = await AsyncAuthService.create_user(
        db=db,
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        is_superuser=user_in.is_superuser,
        tenant_id=str(user_in.tenant_id)
    )
    
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Obtiene información detallada de un usuario (solo administradores).
    """
    stmt = select(User).filter(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Actualiza un usuario existente (solo administradores).
    """
    stmt = select(User).filter(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Verificar email duplicado si se está cambiando
    if user_in.email and user_in.email != user.email:
        stmt = select(User).filter(User.email == user_in.email)
        result = await db.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            raise HTTPException(
                status_code=400,
                detail="El email ya está registrado"
            )
    
    # Verificar que el tenant exista si se está cambiando
    if user_in.tenant_id and user_in.tenant_id != user.tenant_id:
        stmt = select(Tenant).filter(Tenant.id == user_in.tenant_id)
        result = await db.execute(stmt)
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail="Tenant no encontrado"
            )
    
    # Actualizar campos
    update_data = user_in.dict(exclude_unset=True, exclude={"password"})
    for key, value in update_data.items():
        setattr(user, key, value)
    
    # Actualizar contraseña si se proporciona
    if user_in.password:
        from app.core.security import get_password_hash
        user.hashed_password = get_password_hash(user_in.password)
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Elimina un usuario (solo administradores).
    """
    stmt = select(User).filter(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Evitar eliminar al propio usuario administrador
    if str(user.id) == str(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="No puedes eliminar tu propio usuario"
        )
    
    # Eliminar usuario
    db.delete(user)
    await db.commit()
    
    return {"message": f"Usuario {user_id} eliminado exitosamente"}


@router.get("/documents", response_model=dict)
async def list_all_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    tenant_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Lista todos los documentos del sistema (solo administradores).
    """
    # Si se proporciona tenant_id, usar ese tenant
    # Si no, usar el tenant del usuario actual o el tenant por defecto
    if tenant_id:
        tenant_id_str = str(tenant_id)
    else:
        # Usar el tenant del usuario actual como fallback
        tenant_id_str = str(current_user.tenant_id)
    
    document_service = await AsyncDocumentService.create(
        tenant_id=tenant_id_str, 
        user_id=str(current_user.id)
    )
    
    return await document_service.get_documents(
        db=db,
        page=page,
        per_page=per_page
    )


@router.get("/stats", response_model=dict)
async def get_system_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Obtiene estadísticas generales del sistema (solo administradores).
    """
    # Contar usuarios
    stmt = select(func.count(User.id))
    result = await db.execute(stmt)
    total_users = result.scalar() or 0
    
    stmt = select(func.count(User.id)).filter(User.is_active == True)
    result = await db.execute(stmt)
    active_users = result.scalar() or 0
    
    # Contar tenants
    stmt = select(func.count(Tenant.id))
    result = await db.execute(stmt)
    total_tenants = result.scalar() or 0
    
    stmt = select(func.count(Tenant.id)).filter(Tenant.is_active == True)
    result = await db.execute(stmt)
    active_tenants = result.scalar() or 0
    
    # Contar documentos
    stmt = select(func.count(Document.id))
    result = await db.execute(stmt)
    total_documents = result.scalar() or 0
    
    stmt = select(func.count(Document.id)).filter(Document.indexed == 1)
    result = await db.execute(stmt)
    indexed_documents = result.scalar() or 0
    
    stmt = select(func.count(Document.id)).filter(Document.indexed == 2)
    result = await db.execute(stmt)
    error_documents = result.scalar() or 0
    
    # Calcular tamaño total de almacenamiento
    stmt = select(func.sum(Document.file_size))
    result = await db.execute(stmt)
    storage_size = result.scalar() or 0
    
    # Contar documentos por tipo
    stmt = select(
        Document.file_type, 
        func.count(Document.id)
    ).group_by(Document.file_type)
    result = await db.execute(stmt)
    doc_types = result.all()
    
    doc_type_stats = {
        file_type: count for file_type, count in doc_types
    }
    
    return {
        "users": {
            "total": total_users,
            "active": active_users
        },
        "tenants": {
            "total": total_tenants,
            "active": active_tenants
        },
        "documents": {
            "total": total_documents,
            "indexed": indexed_documents,
            "error": error_documents,
            "by_type": doc_type_stats
        },
        "storage": {
            "total_bytes": storage_size,
            "total_mb": round(storage_size / (1024 * 1024), 2)
        }
    }


@router.post("/init-ollama-model", response_model=dict)
async def initialize_ollama_model(
    model_name: str = Body(..., embed=True),
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Inicializa un modelo en Ollama si no está disponible (solo administradores).
    """
    import requests
    from app.core.config import settings
    
    try:
        # Verificar si el modelo ya está disponible
        response = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            
            # Verificar si el modelo ya está descargado
            for model in models:
                if model.get("name") == model_name:
                    return {"message": f"El modelo {model_name} ya está disponible"}
        
        # Iniciar descarga del modelo
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/pull",
            json={"name": model_name}
        )
        
        if response.status_code == 200:
            return {"message": f"Modelo {model_name} descargado exitosamente"}
        else:
            return {
                "message": f"Error al descargar modelo: {response.status_code}",
                "details": response.text
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al interactuar con Ollama: {str(e)}"
        )


@router.get("/stats/document-activity", response_model=Dict[str, Any])
async def get_document_activity_stats(
    time_period_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_active_superuser_async)
):
    """Obtiene estadísticas de actividad de documentos para el panel de administrador"""
    try:
        tenant_id = str(current_user.tenant_id)
        cutoff_date = datetime.now() - timedelta(days=time_period_days)
        
        # Estadísticas generales
        stmt = select(
            func.count(DocumentView.c.id).label("total_views"),
            func.count(func.distinct(DocumentView.c.document_id)).label("documents_viewed"),
            func.count(func.distinct(DocumentView.c.user_id)).label("active_users")
        ).filter(
            DocumentView.c.tenant_id == tenant_id,
            DocumentView.c.viewed_at >= cutoff_date
        )
        result = await db.execute(stmt)
        general_stats = result.first()
        
        # Formatos más populares
        stmt = select(
            Document.file_type,
            func.count(DocumentView.c.id).label("view_count")
        ).join(
            DocumentView, Document.id == DocumentView.c.document_id
        ).filter(
            DocumentView.c.tenant_id == tenant_id,
            DocumentView.c.viewed_at >= cutoff_date
        ).group_by(
            Document.file_type
        ).order_by(
            desc("view_count")
        ).limit(5)
        result = await db.execute(stmt)
        top_formats = result.all()
        
        # Usuarios más activos
        stmt = select(
            User.id,
            User.email,
            User.full_name,
            func.count(DocumentView.c.id).label("view_count")
        ).join(
            DocumentView, User.id == DocumentView.c.user_id
        ).filter(
            DocumentView.c.tenant_id == tenant_id,
            DocumentView.c.viewed_at >= cutoff_date
        ).group_by(
            User.id
        ).order_by(
            desc("view_count")
        ).limit(5)
        result = await db.execute(stmt)
        top_users = result.all()
        
        # Documentos más consultados
        stmt = select(
            Document.id,
            Document.title,
            DocumentMetrics.query_count
        ).join(
            DocumentMetrics, Document.id == DocumentMetrics.document_id
        ).filter(
            Document.tenant_id == tenant_id,
            DocumentMetrics.query_count > 0
        ).order_by(
            desc(DocumentMetrics.query_count)
        ).limit(5)
        result = await db.execute(stmt)
        top_queried_docs = result.all()
        
        # Formatear resultados
        return {
            "general": {
                "total_views": general_stats.total_views if general_stats else 0,
                "documents_viewed": general_stats.documents_viewed if general_stats else 0,
                "active_users": general_stats.active_users if general_stats else 0,
            },
            "top_formats": [{"format": f[0], "count": f[1]} for f in top_formats],
            "top_users": [{
                "id": u[0],
                "email": u[1],
                "name": u[2],
                "view_count": u[3]
            } for u in top_users],
            "top_queried_docs": [{
                "id": d[0],
                "title": d[1],
                "query_count": d[2]
            } for d in top_queried_docs]
        }
    except Exception as e:
        logger.error(f"Error al obtener estadísticas de actividad: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")