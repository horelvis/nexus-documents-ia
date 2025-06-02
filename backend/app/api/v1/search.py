from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.dependencies import get_current_user, get_current_tenant_id
from app.db.models import User
from app.services.search_service import SearchService
from app.schemas.document import ChatMessage

router = APIRouter()


@router.get("/", response_model=List[dict])
async def search_documents(
    query: str = Query(..., description="Texto de búsqueda"),
    limit: int = Query(10, ge=1, le=50),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    
    results = search_service.semantic_search(
        query=query,
        limit=limit,
        filters=filters
    )
    
    return results


@router.post("/ask", response_model=dict)
async def ask_documents(
    message: ChatMessage,
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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