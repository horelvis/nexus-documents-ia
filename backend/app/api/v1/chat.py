from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import logging
from app.api.async_dependencies import (
    get_current_user_async, 
    get_current_tenant_id_async,
    require_subscription_permission_async
)
from app.db.async_database import get_async_db
from app.db.models import User
from app.schemas.document import ChatMessage
from app.services.search_service import SearchService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=dict)
async def chat_with_documents(
    message: ChatMessage,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_subscription_permission_async("can_use_chat")),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Envía un mensaje para chatear con los documentos y obtiene una respuesta.
    """
    search_service = SearchService(tenant_id=tenant_id)
    
    # Convertir UUID a string si es necesario
    doc_ids = [str(doc_id) for doc_id in message.doc_ids] if message.doc_ids else None
    
    result = await search_service.ask_documents(
        question=message.question,
        doc_ids=doc_ids
    )
    
    return result


@router.post("/suggest-tags", response_model=dict)
async def suggest_document_tags(
    text: str = Body(..., embed=True),
    num_tags: int = Body(5, embed=True),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Sugiere etiquetas basadas en el contenido de texto proporcionado.
    """
    llm_service = LLMService()
    suggested_tags = await llm_service.suggest_tags(text, num_tags)
    
    return {"suggested_tags": suggested_tags}


@router.post("/extract-metadata", response_model=dict)
async def extract_document_metadata(
    text: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Extrae metadatos estructurados del texto proporcionado.
    """
    llm_service = LLMService()
    metadata = await llm_service.extract_metadata(text)
    
    return {"metadata": metadata}