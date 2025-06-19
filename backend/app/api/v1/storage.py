from typing import List

from fastapi import APIRouter, Depends, Query, HTTPException
from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async, get_current_active_superuser_async
from app.db.models import User
from app.schemas.document import UploadRequest
from app.services.storage_service import StorageService

router = APIRouter()


# Signed URL endpoints removed for security reasons
# Use storage microservice proxy endpoints instead


@router.get("/list", response_model=List[dict])
async def list_files(
    prefix: str = Query("", description="Prefijo para filtrar archivos"),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Lista los archivos en el almacenamiento del tenant.
    """
    storage_service = StorageService(tenant_id=tenant_id)
    
    files = storage_service.list_files(prefix=prefix)
    
    return files


@router.delete("/{object_name:path}", response_model=dict)
async def delete_file(
    object_name: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Elimina un archivo del almacenamiento.
    """
    storage_service = StorageService(tenant_id=tenant_id)
    
    # Validar que el usuario tenga acceso al objeto
    # Aquí podría implementarse una verificación de acceso más detallada
    
    success = storage_service.delete_file(object_name=object_name)
    
    if not success:
        raise HTTPException(status_code=404, detail="El archivo no existe o no pudo ser eliminado")
    
    return {"message": f"Archivo {object_name} eliminado exitosamente"}


@router.get("/buckets", response_model=List[str])
async def list_buckets(
    current_user: User = Depends(get_current_active_superuser_async)
):
    """
    Lista todos los buckets disponibles (solo administradores).
    """
    from google.cloud import storage
    
    # Esta funcionalidad solo está disponible para superusuarios
    try:
        storage_client = storage.Client()
        buckets = storage_client.list_buckets()
        
        return [bucket.name for bucket in buckets]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar buckets: {str(e)}")