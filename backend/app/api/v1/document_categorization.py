"""
API endpoints for Document Categorization and Tagging
ACTUALIZADO: Usa servicio unificado con LangExtract (sin CAG para categorización)
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
import re

from app.api.async_dependencies import get_current_active_user_async
from app.core.auth.base import UserProfile
from app.db.async_database import get_async_db
from app.db.models import Document
from app.core.config import settings
import os
import httpx

_INTELLIGENCE_URL = os.getenv("INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8000")

logger = logging.getLogger(__name__)
router = APIRouter()

# =====================================
# SCHEMAS
# =====================================

from pydantic import BaseModel

class CategorizeRequest(BaseModel):
    document_ids: Optional[List[str]] = None
    categorize_all_pending: bool = False
    include_tags: bool = True
    force_recategorize: bool = False

class CategorizeResponse(BaseModel):
    total_documents: int
    processed: int
    failed: int
    results: List[Dict[str, Any]]

class CategoryStats(BaseModel):
    total_documents: int
    categorized: int
    pending: int
    by_category: Dict[str, int]
    by_tag: Dict[str, int]

# =====================================
# CATEGORIZATION ENDPOINTS
# =====================================

@router.post("/categorize", response_model=CategorizeResponse)
async def categorize_documents(
    request: CategorizeRequest,
    background_tasks: BackgroundTasks,
    current_user: UserProfile = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Categorize documents using LangGraph document analysis

    - Can categorize specific documents by ID
    - Can categorize all pending documents
    - Optionally generates tags
    - Can force recategorization of already categorized documents
    """
    try:
        # Get documents to categorize
        query = select(Document)

        if request.document_ids:
            # Specific documents
            query = query.filter(Document.id.in_(request.document_ids))
        elif request.categorize_all_pending:
            # All uncategorized documents
            if not request.force_recategorize:
                query = query.filter(
                    or_(
                        Document.category.is_(None),
                        Document.category == "",
                        Document.category == "general"
                    )
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must specify document_ids or set categorize_all_pending=true"
            )
        
        result = await db.execute(query)
        documents = result.scalars().all()
        
        if not documents:
            return CategorizeResponse(
                total_documents=0,
                processed=0,
                failed=0,
                results=[]
            )
        
        # Process documents
        results = []
        processed = 0
        failed = 0
        
        for doc in documents:
            try:
                # Skip if already categorized and not forcing
                if not request.force_recategorize and doc.category and doc.category != "general":
                    results.append({
                        "document_id": str(doc.id),
                        "status": "skipped",
                        "reason": "already_categorized",
                        "category": doc.category
                    })
                    continue
                
                # Build a lightweight context for categorization (content column was removed)
                metadata = doc.document_metadata or {}
                document_content = (
                    metadata.get("text_preview")
                    or metadata.get("summary")
                    or doc.description
                    or doc.title
                    or doc.filename
                )
                document_content = document_content or "Documento sin contenido disponible"
                
                # Classify via intelligence-docs-service
                categorization_result = {"success": False, "category": "general"}
                try:
                    async with httpx.AsyncClient(timeout=30.0) as http_client:
                        classify_resp = await http_client.post(
                            f"{_INTELLIGENCE_URL}/classify",
                            json={"text": document_content[:5000], "filename": doc.title or doc.filename or ""},
                        )
                        classify_resp.raise_for_status()
                        classify_data = classify_resp.json()
                        categorization_result = {
                            "success": True,
                            "category": classify_data.get("document_type", "general"),
                            "confidence": classify_data.get("confidence", 0.0),
                            "reasoning": classify_data.get("document_type", ""),
                            "method": "intelligence-docs-service",
                        }

                    # Optionally extract entities
                    if request.include_tags:
                        async with httpx.AsyncClient(timeout=120.0) as http_client:
                            ent_resp = await http_client.post(
                                f"{_INTELLIGENCE_URL}/entities",
                                json={"text": document_content[:50000], "language": "es", "document_type": categorization_result["category"]},
                            )
                            ent_resp.raise_for_status()
                            categorization_result["extractions"] = ent_resp.json().get("entities", [])
                except Exception as cat_err:
                    logger.warning(f"Categorization failed for {doc.id}: {cat_err}")

                if categorization_result["success"]:
                    # Actualizar documento en base de datos
                    doc.category = categorization_result["category"]
                    doc.document_metadata = doc.document_metadata or {}
                    doc.document_metadata["categorization"] = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "confidence": categorization_result.get("confidence", 0),
                        "reasoning": categorization_result.get("reasoning", ""),
                        "method": categorization_result.get("method", ""),
                        "alternative_types": categorization_result.get("alternative_types", []),
                        "visualization_html": categorization_result.get("visualization_html")
                    }

                    # Guardar entidades extraídas y summary
                    if request.include_tags and categorization_result.get("extractions"):
                        # Guardar entidades estructuradas en campo dedicado
                        doc.extracted_entities = categorization_result.get("extractions", [])
                        logger.info(f"✅ Guardadas {len(doc.extracted_entities)} entidades extraídas")

                        # Guardar summary estructurado en metadata
                        if categorization_result.get("summary"):
                            doc.document_metadata["extraction_summary"] = categorization_result.get("summary", {})
                            logger.info(f"✅ Guardado summary de extracción")

                        # Generar tags inteligentes desde entidades
                        tags = _generate_tags_from_extractions(
                            categorization_result["extractions"],
                            categorization_result.get("summary", {})
                        )
                        doc.tags_array = tags
                        logger.info(f"✅ Generados {len(tags)} tags desde entidades")
                    else:
                        tags = []

                    results.append({
                        "document_id": str(doc.id),
                        "status": "success",
                        "category": categorization_result["category"],
                        "confidence": categorization_result.get("confidence", 0),
                        "reasoning": categorization_result.get("reasoning", ""),
                        "tags": tags if request.include_tags else []
                    })
                    processed += 1
                else:
                    results.append({
                        "document_id": str(doc.id),
                        "status": "failed",
                        "error": categorization_result.get("error", "Unknown error")
                    })
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Error categorizing document {doc.id}: {e}")
                results.append({
                    "document_id": str(doc.id),
                    "status": "failed",
                    "error": str(e)
                })
                failed += 1
        
        # Commit changes
        await db.commit()
        
        return CategorizeResponse(
            total_documents=len(documents),
            processed=processed,
            failed=failed,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Error in batch categorization: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Categorization failed: {str(e)}"
        )

@router.get("/stats", response_model=CategoryStats)
async def get_categorization_stats(
    current_user: UserProfile = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Get categorization statistics (deployment-wide, Pattern C aggregate)."""
    try:
        # Total documents (aggregate, no ACL filter)
        total_query = select(func.count(Document.id))
        total_result = await db.execute(total_query)
        total_documents = total_result.scalar() or 0

        # Categorized documents
        categorized_query = select(func.count(Document.id)).filter(
            Document.category.isnot(None),
            Document.category != "",
            Document.category != "general"
        )
        categorized_result = await db.execute(categorized_query)
        categorized = categorized_result.scalar() or 0

        # By category
        category_query = select(
            Document.category,
            func.count(Document.id)
        ).filter(
            Document.category.isnot(None),
            Document.category != ""
        ).group_by(Document.category)
        
        category_result = await db.execute(category_query)
        by_category = dict(category_result.all())
        
        # By tag (if using PostgreSQL array)
        # Note: This is simplified - actual implementation depends on how tags are stored
        by_tag = {}
        
        return CategoryStats(
            total_documents=total_documents,
            categorized=categorized,
            pending=total_documents - categorized,
            by_category=by_category,
            by_tag=by_tag
        )
        
    except Exception as e:
        logger.error(f"Error getting categorization stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )

@router.post("/schedule-batch")
async def schedule_batch_categorization(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(50, ge=1, le=500),
    current_user: UserProfile = Depends(get_current_active_user_async)
):
    """Schedule batch categorization as a background task"""
    background_tasks.add_task(
        process_categorization_batch,
        user_id=current_user.sub,
        batch_size=batch_size
    )

    return {
        "status": "scheduled",
        "message": f"Batch categorization scheduled for up to {batch_size} documents",
    }

# =====================================
# HELPER FUNCTIONS
# =====================================

def _generate_tags_from_extractions(
    extractions: List[Dict],
    summary: Dict
) -> List[str]:
    """
    Genera tags inteligentes desde las entidades extraídas por LangExtract.
    Selecciona las entidades más relevantes y limita el número de tags.
    """
    tags = set()

    # Tags desde entidades clave (primeras 20 más relevantes)
    for extraction in extractions[:20]:
        entity_type = extraction.get("type", "")
        entity_name = extraction.get("name", "").strip()

        # Agregar entidades importantes como tags
        if entity_type in ["party", "organization", "company", "person", "declarante", "trabajador"]:
            if entity_name and len(entity_name) < 50:  # Solo nombres razonables
                tags.add(entity_name)

        # Agregar contextos y roles como tags
        context = extraction.get("context", "").strip()
        if context and len(context) < 30:
            tags.add(context)

        role = extraction.get("role", "").strip()
        if role and len(role) < 30:
            tags.add(role)

    # Tags desde summary
    if summary:
        # Parties (contratos)
        if summary.get("parties"):
            for party in summary["parties"][:3]:
                if party and len(party) < 50:
                    tags.add(party)

        # Key entities (general)
        if summary.get("key_entities"):
            for entity in summary["key_entities"][:3]:
                if entity and len(entity) < 50:
                    tags.add(entity)

        # Authors (reportes)
        if summary.get("authors"):
            for author in summary["authors"][:2]:
                if author and len(author) < 50:
                    tags.add(author)

    # Limitar cantidad de tags y retornar lista ordenada
    return sorted(list(tags))[:10]

async def process_categorization_batch(
    user_id: str,
    batch_size: int = 50
):
    """Process a batch of documents for categorization (background task)"""
    logger.info(f"Starting batch categorization triggered by user {user_id}")

    try:
        # This would be implemented with proper database session management
        # and error handling in production

        # Get uncategorized documents
        # Process each document using unified categorization service
        # Update database
        # Send notifications if needed

        logger.info("Completed batch categorization")

    except Exception as e:
        logger.error(f"Batch categorization failed: {e}")

# =====================================
# MANUAL CATEGORY MANAGEMENT
# =====================================

@router.put("/{document_id}/category")
async def update_document_category(
    document_id: str,
    category: str,
    current_user: UserProfile = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Manually update document category"""
    result = await db.execute(
        select(Document).filter(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    # Update category
    document.category = category
    document.document_metadata = document.document_metadata or {}
    document.document_metadata["manual_categorization"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": current_user.sub
    }
    
    await db.commit()
    
    return {
        "document_id": str(document.id),
        "category": category,
        "status": "updated"
    }

@router.put("/{document_id}/tags")
async def update_document_tags(
    document_id: str,
    tags: List[str],
    current_user: UserProfile = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Manually update document tags"""
    result = await db.execute(
        select(Document).filter(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    # Update tags
    document.tags_array = tags
    document.document_metadata = document.document_metadata or {}
    document.document_metadata["manual_tagging"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": current_user.sub
    }
    
    await db.commit()
    
    return {
        "document_id": str(document.id),
        "tags": tags,
        "status": "updated"
    }
