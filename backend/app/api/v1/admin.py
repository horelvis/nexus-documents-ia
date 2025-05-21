from datetime import datetime, timedelta
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.dependencies import get_current_active_superuser
from app.db.database import SessionLocal, get_db
from app.db.models import User, Tenant, Document
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService

router = APIRouter()


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    tenant_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Lista todos los usuarios del sistema (solo administradores).
    """
    query = db.query(User)
    
    if tenant_id:
        query = query.filter(User.tenant_id == tenant_id)
    
    users = query.offset(skip).limit(limit).all()
    return users


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Crea un nuevo usuario (solo administradores).
    """
    # Verificar si el email ya existe
    db_user = db.query(User).filter(User.email == user_in.email).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="El email ya está registrado"
        )
    
    # Verificar que el tenant exista
    tenant = db.query(Tenant).filter(Tenant.id == user_in.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant no encontrado"
        )
    
    # Crear usuario
    user = AuthService.create_user(
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Obtiene información detallada de un usuario (solo administradores).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Actualiza un usuario existente (solo administradores).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Verificar email duplicado si se está cambiando
    if user_in.email and user_in.email != user.email:
        db_user = db.query(User).filter(User.email == user_in.email).first()
        if db_user:
            raise HTTPException(
                status_code=400,
                detail="El email ya está registrado"
            )
    
    # Verificar que el tenant exista si se está cambiando
    if user_in.tenant_id and user_in.tenant_id != user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user_in.tenant_id).first()
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
    db.commit()
    db.refresh(user)
    
    return user


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Elimina un usuario (solo administradores).
    """
    user = db.query(User).filter(User.id == user_id).first()
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
    db.commit()
    
    return {"message": f"Usuario {user_id} eliminado exitosamente"}


@router.get("/documents", response_model=dict)
async def list_all_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    tenant_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Lista todos los documentos del sistema (solo administradores).
    """
    # Si se proporciona tenant_id, filtrar por ese tenant
    # Si no, mostrar documentos de todos los tenants
    tenant_id_str = str(tenant_id) if tenant_id else None
    
    document_service = DocumentService(
        tenant_id=tenant_id_str, 
        user_id=str(current_user.id)
    )
    
    return document_service.get_documents(
        page=page,
        per_page=per_page
    )


@router.get("/stats", response_model=dict)
async def get_system_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Obtiene estadísticas generales del sistema (solo administradores).
    """
    # Contar usuarios
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    
    # Contar tenants
    total_tenants = db.query(Tenant).count()
    active_tenants = db.query(Tenant).filter(Tenant.is_active == True).count()
    
    # Contar documentos
    total_documents = db.query(Document).count()
    indexed_documents = db.query(Document).filter(Document.indexed == 1).count()
    error_documents = db.query(Document).filter(Document.indexed == 2).count()
    
    # Calcular tamaño total de almacenamiento
    storage_size = db.query(Document.file_size).with_entities(
        db.func.sum(Document.file_size)
    ).scalar() or 0
    
    # Contar documentos por tipo
    doc_types = db.query(
        Document.file_type, 
        db.func.count(Document.id)
    ).group_by(Document.file_type).all()
    
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_superuser)
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
def get_document_activity_stats(
    time_period_days: int = Query(30, ge=1, le=365),
    current_user = Depends(get_current_admin_user)
):
    """Obtiene estadísticas de actividad de documentos para el panel de administrador"""
    db = SessionLocal()
    try:
        tenant_id = str(current_user.tenant_id)
        cutoff_date = datetime.now() - timedelta(days=time_period_days)
        
        # Estadísticas generales
        general_stats = db.query(
            func.count(document_views.c.id).label("total_views"),
            func.count(func.distinct(document_views.c.document_id)).label("documents_viewed"),
            func.count(func.distinct(document_views.c.user_id)).label("active_users")
        ).filter(
            document_views.c.tenant_id == tenant_id,
            document_views.c.viewed_at >= cutoff_date
        ).first()
        
        # Formatos más populares
        top_formats = db.query(
            Document.format,
            func.count(document_views.c.id).label("view_count")
        ).join(
            document_views, Document.id == document_views.c.document_id
        ).filter(
            document_views.c.tenant_id == tenant_id,
            document_views.c.viewed_at >= cutoff_date
        ).group_by(
            Document.format
        ).order_by(
            desc("view_count")
        ).limit(5).all()
        
        # Usuarios más activos
        top_users = db.query(
            User.id,
            User.email,
            User.name,
            func.count(document_views.c.id).label("view_count")
        ).join(
            document_views, User.id == document_views.c.user_id
        ).filter(
            document_views.c.tenant_id == tenant_id,
            document_views.c.viewed_at >= cutoff_date
        ).group_by(
            User.id
        ).order_by(
            desc("view_count")
        ).limit(5).all()
        
        # Documentos más consultados
        top_queried_docs = db.query(
            Document.id,
            Document.title,
            DocumentMetrics.query_count
        ).join(
            DocumentMetrics, Document.id == DocumentMetrics.document_id
        ).filter(
            Document.tenant_id == tenant_id,
            DocumentMetrics.query_count > 0,
            Document.is_deleted == False
        ).order_by(
            desc(DocumentMetrics.query_count)
        ).limit(5).all()
        
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
    finally:
        db.close()