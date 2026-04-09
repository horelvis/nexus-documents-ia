"""
Internal API endpoints for connector data access.

These endpoints are for internal microservice communication only.
Authentication is via X-API-Key header, not user tokens.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.async_database import get_async_db
from app.db.models import IndexedDocument

logger = logging.getLogger(__name__)

router = APIRouter()


async def verify_internal_api_key(
    x_api_key: str = Header(..., alias="X-API-Key")
) -> str:
    """Verify the internal microservice API key."""
    expected_key = getattr(settings, 'MICROSERVICES_API_KEY', None)
    if not expected_key or x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


@router.get("/indexed-documents")
async def get_indexed_documents_internal(
    status: Optional[str] = Query("indexed", description="Filter by indexing status"),
    limit: Optional[int] = Query(1000, ge=1, le=5000, description="Maximum documents to return"),
    connector_id: Optional[str] = Query(None, description="Filter by connector ID"),
    db: AsyncSession = Depends(get_async_db),
    _api_key: str = Depends(verify_internal_api_key),
):
    """
    Get all indexed documents (internal API for SIL reindexing).

    This endpoint is used by the SIL (Structural Intelligence Layer) service
    to fetch documents that need to be indexed to the structural graph.

    Returns documents from IndexedDocument table (connector-sourced documents).

    Authentication: X-API-Key header required (microservice API key).
    """
    try:
        # Build query for indexed documents
        query = select(IndexedDocument)

        # Filter by status if provided
        if status:
            query = query.where(IndexedDocument.indexing_status == status)

        # Filter by connector if provided
        if connector_id:
            query = query.where(IndexedDocument.connector_id == UUID(connector_id))

        # Apply limit
        query = query.order_by(IndexedDocument.created_at.desc()).limit(limit)

        result = await db.execute(query)
        documents = result.scalars().all()

        logger.info(f"Internal API: Returning {len(documents)} indexed documents")

        # Return in format expected by SIL service
        return {
            "documents": [
                {
                    "id": str(doc.id),
                    "connector_id": str(doc.connector_id) if doc.connector_id else None,
                    "external_id": doc.external_id,
                    "external_path": doc.external_path,
                    "title": doc.title,
                    "description": doc.description,
                    "mime_type": doc.mime_type,
                    "file_extension": doc.file_extension,
                    "size_bytes": doc.size_bytes,
                    "source_metadata": doc.source_metadata or {},
                    "learned_context": doc.learned_context or {},
                    "weaviate_id": str(doc.weaviate_id) if doc.weaviate_id else None,
                    "indexing_status": doc.indexing_status,
                    "source_created_at": doc.source_created_at.isoformat() if doc.source_created_at else None,
                    "source_modified_at": doc.source_modified_at.isoformat() if doc.source_modified_at else None,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                }
                for doc in documents
            ],
            "total": len(documents),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {e}")
    except Exception as e:
        logger.error(f"Error fetching indexed documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
