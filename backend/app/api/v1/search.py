from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.models import User
from app.services.search_service import SearchService
from app.services.vector_service import VectorService
from app.services.reindex_service import ReindexService
from app.schemas.document import ChatMessage

router = APIRouter()


@router.get("/", response_model=List[dict])
async def search_documents(
    query: str = Query(..., description="Texto de búsqueda"),
    limit: int = Query(10, ge=1, le=50),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Realiza una búsqueda semántica entre los documentos.
    """
    search_service = SearchService(tenant_id=tenant_id)
    
    # Preparar filtros
    filters = {}
    if tags:
        filters["tags"] = tags
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    
    results = await search_service.search_documents(
        query=query,
        limit=limit
    )
    
    return results


@router.post("/ask", response_model=dict)
async def ask_documents(
    message: ChatMessage,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Responde a una pregunta basada en los documentos.
    """
    search_service = SearchService(tenant_id=tenant_id)
    
    # Convertir UUID a string si es necesario
    doc_ids = [str(doc_id) for doc_id in message.doc_ids] if message.doc_ids else None
    
    result = await search_service.ask_documents(
        question=message.question,
        doc_ids=doc_ids
    )
    
    return result


@router.get("/health", response_model=dict)
async def check_search_system_health(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Verifica la salud del sistema de búsqueda semántica.
    """
    vector_service = VectorService(tenant_id=tenant_id)
    health_info = await vector_service.check_system_health()
    
    return health_info


@router.post("/fix-embedding-model", response_model=dict)
async def fix_embedding_model(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Intenta descargar automáticamente el modelo de embeddings si falta.
    """
    vector_service = VectorService(tenant_id=tenant_id)
    success = await vector_service._ensure_embedding_model()
    
    if success:
        return {
            "message": "Embedding model is now available",
            "success": True
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to ensure embedding model availability"
        )


@router.get("/reindex/status", response_model=dict)
async def get_reindex_status(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Obtiene el estado del reindexado para el tenant actual.
    """
    reindex_service = ReindexService(tenant_id=tenant_id)
    status = await reindex_service.check_reindex_status()
    return status


@router.post("/reindex/all", response_model=dict)
async def reindex_all_documents(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Reindexa todos los documentos que faltan en el vector store.
    """
    reindex_service = ReindexService(tenant_id=tenant_id)
    result = await reindex_service.reindex_all_missing()
    return result


@router.post("/reindex/documents", response_model=dict)
async def reindex_specific_documents(
    document_ids: List[str],
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Reindexa documentos específicos por sus IDs.
    """
    if not document_ids:
        raise HTTPException(status_code=400, detail="Document IDs list cannot be empty")
    
    reindex_service = ReindexService(tenant_id=tenant_id)
    result = await reindex_service.reindex_specific_documents(document_ids)
    return result


@router.post("/fix-and-reindex", response_model=dict)
async def fix_collection_and_reindex(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Arregla problemas de dimensiones y reindexa automáticamente.
    """
    vector_service = VectorService(tenant_id=tenant_id)
    
    # Trigger dimension fix
    fix_success = await vector_service._auto_fix_dimension_mismatch()
    
    if fix_success:
        return {
            "message": "Collection fix and reindexing initiated successfully",
            "status": "in_progress",
            "success": True
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate collection fix and reindexing"
        )