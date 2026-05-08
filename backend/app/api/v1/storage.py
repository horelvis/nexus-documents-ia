from typing import List

from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.auth.superuser import require_superuser
from app.services.async_storage_service import AsyncStorageService

router = APIRouter()


# Signed URL endpoints removed for security reasons
# Use storage microservice proxy endpoints instead


@router.get("/list", response_model=List[dict])
async def list_files(
    prefix: str = Query("", description="Prefijo para filtrar archivos"),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Lista los archivos en el almacenamiento.
    """
    storage_service = AsyncStorageService()

    files = await storage_service.list_files(prefix=prefix)

    return files


@router.delete("/{object_name:path}", response_model=dict)
async def delete_file(
    object_name: str,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Elimina un archivo del almacenamiento.
    """
    storage_service = AsyncStorageService()

    success = await storage_service.delete_file(object_name=object_name)

    if not success:
        raise HTTPException(status_code=404, detail="El archivo no existe o no pudo ser eliminado")

    return {"message": f"Archivo {object_name} eliminado exitosamente"}


@router.get("/buckets", response_model=List[str])
async def list_buckets(
    current_user: UserProfile = Depends(require_superuser),
):
    """
    Lista todos los buckets disponibles (solo administradores).
    """
    from google.cloud import storage

    try:
        storage_client = storage.Client()
        buckets = storage_client.list_buckets()

        return [bucket.name for bucket in buckets]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar buckets: {str(e)}")
