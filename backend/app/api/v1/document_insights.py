# app/api/endpoints/document_insights.py

from fastapi import APIRouter, Depends, Query
from typing import List
from app.schemas.document import DocumentWithMetrics, DocumentBasic
from app.services.async_document_service import AsyncDocumentService
from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.db.async_database import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/recently-viewed")
async def get_recently_viewed_documents(
    limit: int = Query(10, ge=1, le=50),
    user_specific: bool = Query(True),
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Obtiene los documentos vistos recientemente por el usuario."""
    try:
        from sqlalchemy import select, func
        from app.db.models import Document, DocumentView

        # Base query with Document and DocumentView joined
        query = select(
            Document,
            func.max(DocumentView.viewed_at).label("last_viewed_at")
        ).join(
            DocumentView, Document.id == DocumentView.document_id
        )

        # Filter by user if specified
        if user_specific and current_user.sub:
            query = query.filter(DocumentView.user_id == current_user.sub)
        
        # Group by document, order by most recent view, limit results
        query = query.group_by(Document.id).order_by(
            func.max(DocumentView.viewed_at).desc()
        ).limit(limit)
        
        result = await db.execute(query)
        documents = result.fetchall()
        
        # Format results
        results = []
        for doc, last_viewed_at in documents:
            results.append({
                "id": str(doc.id),
                "filename": doc.filename,
                "title": doc.title,
                "description": doc.description,
                "file_type": doc.file_type,
                "mime_type": doc.mime_type,
                "file_size": doc.file_size,
                "tags": doc.tags or [],
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "indexed": doc.indexed,
                "category": doc.category,
                "created_by": str(doc.created_by),
                "last_viewed_at": last_viewed_at.isoformat() if last_viewed_at else None
            })
        
        logger.info(f"Retrieved {len(results)} recently viewed documents")
        return results
        
    except Exception as e:
        logger.error(f"Error getting recently viewed documents: {str(e)}")
        return []

@router.post("/mark-viewed")
async def mark_document_as_viewed(
    document_id: str,
    view_duration_seconds: int = Query(None),
    scroll_percentage: float = Query(None),
    current_user = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db),
):
    """Marca un documento como visto por el usuario actual"""
    try:
        document_service = await AsyncDocumentService.create(user=current_user, db=db)

        view_id = await document_service.mark_document_viewed(
            document_id=document_id,
            view_duration_seconds=view_duration_seconds,
            scroll_percentage=scroll_percentage,
        )

        return {
            "success": True,
            "view_id": str(view_id),
            "message": "Document marked as viewed",
        }
            
    except Exception as e:
        logger.error(f"Error marking document as viewed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
