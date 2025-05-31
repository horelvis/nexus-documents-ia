from typing import List

from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_current_user, get_current_tenant_id, get_current_active_superuser
from app.db.models import User
from app.schemas.document import SignedUrlResponse, UploadRequest
from app.services.storage_service import StorageService

router = APIRouter()


@router.post("/upload-url", response_model=SignedUrlResponse)
async def generate_upload_url(
    request: UploadRequest,
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Genera una URL firmada para subir un archivo directamente al almacenamiento.
    """
    storage_service = StorageService(tenant_id=tenant_id)
    
    url, expires_at = storage_service.generate_upload_signed_url(
        object_name=f"uploads/{current_user.id}/{request.filename}",
        content_type=request.content_type
    )
    
    return {
        "url": url,
        "expires_at": expires_at.isoformat()
    }


@router.post("/download-url", response_model=SignedUrlResponse)
async def generate_download_url(
    object_name: str,
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Genera una URL firmada para descargar un archivo del almacenamiento.
    """
    storage_service = StorageService(tenant_id=tenant_id)
    
    # Validar que el usuario tenga acceso al objeto
    # Aquí podría implementarse una verificación de acceso más detallada
    
    try:
        url, expires_at = storage_service.generate_download_signed_url(
            object_name=object_name
        )
        
        return {
            "url": url,
            "expires_at": expires_at.isoformat()
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="El archivo no existe")


@router.get("/list", response_model=List[dict])
async def list_files(
    prefix: str = Query("", description="Prefijo para filtrar archivos"),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    current_user: User = Depends(get_current_active_superuser)
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