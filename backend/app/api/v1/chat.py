from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from uuid import UUID
import logging
from app.api.dependencies import get_current_user, get_current_tenant_id
from app.db.database import get_db
from app.db.models import User
from app.schemas.document import ChatMessage
from app.services.search_service import SearchService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=dict)
async def chat_with_documents(
    message: ChatMessage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Extrae metadatos estructurados del texto proporcionado.
    """
    llm_service = LLMService()
    metadata = await llm_service.extract_metadata(text)
    
    return {"metadata": metadata}