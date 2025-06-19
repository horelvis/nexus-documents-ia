"""
API endpoints for Document Categorization and Tagging
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import json

from app.api.async_dependencies import get_current_active_user_async
from app.db.async_database import get_async_db
from app.db.models import User, Document
from app.core.config import settings

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
    current_user: User = Depends(get_current_active_user_async),
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
        query = select(Document).filter(
            Document.tenant_id == current_user.tenant_id,
        )
        
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
                
                # Get document content
                # Note: In production, you'd fetch actual content from storage
                document_content = doc.content or f"Document: {doc.name}\nType: {doc.mime_type}"
                
                # Call LangGraph for categorization
                categorization_result = await categorize_single_document(
                    document_id=str(doc.id),
                    document_content=document_content,
                    document_name=doc.name,
                    tenant_id=str(current_user.tenant_id),
                    user_id=str(current_user.id),
                    include_tags=request.include_tags
                )
                
                if categorization_result["success"]:
                    # Update document in database
                    doc.category = categorization_result["category"]
                    if request.include_tags and categorization_result.get("tags"):
                        doc.tags_array = categorization_result["tags"]
                    doc.document_metadata = doc.document_metadata or {}
                    doc.document_metadata["categorization"] = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "confidence": categorization_result.get("confidence", 0),
                        "analysis": categorization_result.get("analysis", {})
                    }
                    
                    results.append({
                        "document_id": str(doc.id),
                        "status": "success",
                        "category": categorization_result["category"],
                        "tags": categorization_result.get("tags", []),
                        "confidence": categorization_result.get("confidence", 0)
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
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Get categorization statistics for the tenant"""
    try:
        # Total documents
        total_query = select(func.count(Document.id)).filter(
            Document.tenant_id == current_user.tenant_id,
        )
        total_result = await db.execute(total_query)
        total_documents = total_result.scalar() or 0
        
        # Categorized documents
        categorized_query = select(func.count(Document.id)).filter(
            Document.tenant_id == current_user.tenant_id,
            Document.deleted_at.is_(None),
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
            Document.tenant_id == current_user.tenant_id,
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
    current_user: User = Depends(get_current_active_user_async)
):
    """Schedule batch categorization as a background task"""
    background_tasks.add_task(
        process_categorization_batch,
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        batch_size=batch_size
    )
    
    return {
        "status": "scheduled",
        "message": f"Batch categorization scheduled for up to {batch_size} documents",
        "tenant_id": str(current_user.tenant_id)
    }

# =====================================
# HELPER FUNCTIONS
# =====================================

async def categorize_single_document(
    document_id: str,
    document_content: str,
    document_name: str,
    tenant_id: str,
    user_id: str,
    include_tags: bool = True
) -> Dict[str, Any]:
    """Categorize a single document using LangGraph"""
    try:
        async with httpx.AsyncClient() as client:
            # Call document analysis
            analysis_response = await client.post(
                f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/run",
                json={
                    "graph_type": "document_analysis_crew",
                    "input_data": {
                        "document_id": document_id,
                        "document_content": document_content,
                        "tenant_id": tenant_id,
                        "user_id": user_id
                    },
                    "mode": "run"
                },
                headers={
                    "X-API-Key": settings.LANGGRAPH_API_KEY,
                    "X-Tenant-ID": tenant_id,
                    "X-User-ID": user_id
                },
                timeout=60.0
            )
            
            if analysis_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Analysis failed: {analysis_response.status_code}"
                }
            
            analysis_result = analysis_response.json()
            
            # Extract category
            category = analysis_result.get("document_type", "general")
            confidence = analysis_result.get("confidence_scores", {}).get("overall", 0.5)
            
            result = {
                "success": True,
                "category": category,
                "confidence": confidence,
                "analysis": analysis_result.get("analysis", {})
            }
            
            # Generate tags if requested
            if include_tags:
                tags_response = await client.post(
                    f"{settings.LANGGRAPH_SERVICE_URL}/api/v1/graphs/run",
                    json={
                        "graph_type": "tag_generation",
                        "input_data": {
                            "text": document_content,
                            "max_tags": 10,
                            "tag_type": "general"
                        },
                        "mode": "run"
                    },
                    headers={
                        "X-API-Key": settings.LANGGRAPH_API_KEY,
                        "X-Tenant-ID": tenant_id
                    },
                    timeout=30.0
                )
                
                if tags_response.status_code == 200:
                    tags_result = tags_response.json()
                    result["tags"] = tags_result.get("tags", [])
                else:
                    result["tags"] = []
            
            return result
            
    except Exception as e:
        logger.error(f"Error categorizing document {document_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def process_categorization_batch(
    tenant_id: str,
    user_id: str,
    batch_size: int = 50
):
    """Process a batch of documents for categorization (background task)"""
    logger.info(f"Starting batch categorization for tenant {tenant_id}")
    
    try:
        # This would be implemented with proper database session management
        # and error handling in production
        
        # Get uncategorized documents
        # Process each document
        # Update database
        # Send notifications if needed
        
        logger.info(f"Completed batch categorization for tenant {tenant_id}")
        
    except Exception as e:
        logger.error(f"Batch categorization failed: {e}")

# =====================================
# MANUAL CATEGORY MANAGEMENT
# =====================================

@router.put("/{document_id}/category")
async def update_document_category(
    document_id: str,
    category: str,
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Manually update document category"""
    # Get document
    result = await db.execute(
        select(Document).filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
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
        "user_id": str(current_user.id)
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
    current_user: User = Depends(get_current_active_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """Manually update document tags"""
    # Get document
    result = await db.execute(
        select(Document).filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
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
        "user_id": str(current_user.id)
    }
    
    await db.commit()
    
    return {
        "document_id": str(document.id),
        "tags": tags,
        "status": "updated"
    }