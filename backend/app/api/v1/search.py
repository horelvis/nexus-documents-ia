"""
Search API endpoints.

Uses UnifiedSearchService which automatically selects the appropriate backend:
- Elasticsearch when Feature.ELASTICSEARCH_SEARCH is enabled
- Weaviate hybrid (BM25 + vector) when disabled

For on-premise Emma-centric deployments, Elasticsearch is disabled by default.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.models import User, Document
from app.services.search_service import SearchService
from app.services.weaviate_client import weaviate_client
from app.services.reindex_service import ReindexService
from app.services.cag_client import CAGClient
from app.services.unified_search_service import (
    UnifiedSearchService,
    SearchUserContext as UnifiedUserContext,
)
from app.core.features import Feature, FeatureFlags
from app.schemas.document import ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/elasticsearch", response_model=List[dict])
async def search_elasticsearch(
    query: str = Query(..., description="Texto de búsqueda"),
    limit: int = Query(10, ge=1, le=100),
    search_type: Optional[str] = Query("hybrid", description="Tipo de búsqueda: hybrid, keyword"),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    SIMPLE Elasticsearch search - no fallbacks
    - hybrid: Elasticsearch (keyword + semantic) 
    - keyword: Elasticsearch (traditional search)
    """
    from app.services.elasticsearch_client import elasticsearch_client, SearchUserContext

    # Prepare filters
    filters = {}
    if tags:
        filters["tags"] = tags
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    # Build user context for ACL filtering
    user_role_ids = [str(role.id) for role in current_user.roles] if current_user.roles else []
    user_context = SearchUserContext(
        user_id=str(current_user.id),
        role_ids=user_role_ids,
        is_admin=current_user.is_admin
    )

    # Direct Elasticsearch microservice search with ACL filtering
    results = await elasticsearch_client.hybrid_search(
        tenant_id=tenant_id,
        query=query,
        limit=limit,
        filters=filters,
        user_context=user_context
    )

    return results


@router.get("/database", response_model=List[dict])
async def search_database(
    query: str = Query(..., description="Texto de búsqueda"),
    limit: int = Query(10, ge=1, le=100),
    tags: Optional[List[str]] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    SIMPLE database search - no fallbacks
    Searches in title, description, content in PostgreSQL
    """
    try:
        from sqlalchemy.future import select
        from sqlalchemy.orm import selectinload
        from sqlalchemy import or_
        from app.db.database import SessionLocal

        with SessionLocal() as db:
            stmt = select(Document).options(
                selectinload(Document.tags)
            ).filter(
                Document.tenant_id == tenant_id
            )

            # Apply search filter - METADATA ONLY (no content search in DB)
            if query:
                stmt = stmt.filter(
                    or_(
                        Document.title.ilike(f"%{query}%"),
                        Document.description.ilike(f"%{query}%"),
                        Document.filename.ilike(f"%{query}%")
                    )
                )

            # Apply other filters
            if category:
                stmt = stmt.filter(Document.category == category)

            stmt = stmt.limit(limit)

            result = db.execute(stmt)
            documents = result.scalars().all()

            # Format results to match expected structure
            formatted_results = []
            for doc in documents:
                try:
                    formatted_results.append({
                        "document": {
                            "id": str(doc.id),
                            "title": doc.title or "",
                            "description": doc.description or "",
                            "filename": doc.filename or "",
                            "file_type": doc.file_type or "",
                            "file_size": doc.file_size or 0,
                            "mime_type": doc.mime_type or "",
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                            "indexed": str(doc.indexed) if doc.indexed is not None else "false",
                            "tenant_id": str(doc.tenant_id),
                            "tags": [tag.name for tag in doc.tags] if doc.tags else []
                        },
                        "score": 1.0,  # Database doesn't provide relevance scoring
                        "matches": []
                    })
                except Exception as e:
                    logger.warning(f"Error formatting document {doc.id}: {e}")
                    continue

            return formatted_results
    except Exception as e:
        logger.error(f"Database search error: {e}")
        # Return empty list instead of raising exception
        return []


@router.get("/", response_model=List[dict])
async def search_documents(
    query: str = Query(..., description="Texto de búsqueda"),
    limit: int = Query(10, ge=1, le=100),
    search_type: Optional[str] = Query("auto", description="Tipo de búsqueda: auto, hybrid, semantic, keyword, database"),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Unified search endpoint using the appropriate backend.

    When Elasticsearch is enabled (SAAS mode):
    - Uses ES for hybrid/keyword search with Weaviate fallback

    When Elasticsearch is disabled (ON_PREMISE mode):
    - Uses Weaviate native hybrid search (BM25 + vector)

    Search types:
    - auto: Automatically select best search type based on query
    - hybrid: Combined keyword + semantic search (default)
    - semantic: Pure vector similarity search
    - keyword: Pure BM25/keyword search
    - database: PostgreSQL metadata search only (fallback)
    """
    try:
        # Build user context for ACL filtering
        user_role_ids = [str(role.id) for role in current_user.roles] if current_user.roles else []
        user_context = UnifiedUserContext(
            user_id=str(current_user.id),
            role_ids=user_role_ids,
            is_admin=current_user.is_admin
        )

        # Database-only search (fallback)
        if search_type == "database":
            return await search_database(query, limit, tags, None, current_user, tenant_id)

        # Prepare filters
        filters = {}
        if tags:
            filters["tags"] = tags
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to

        # Use UnifiedSearchService (auto-selects ES or Weaviate based on feature flags)
        unified_service = UnifiedSearchService(tenant_id=tenant_id)

        # Determine actual search type
        actual_search_type = search_type
        if search_type == "auto":
            actual_search_type = await unified_service.suggest_search_type(query)
            logger.debug(f"Auto-selected search type: {actual_search_type}")
        elif search_type == "elasticsearch":
            # Legacy: map to hybrid
            actual_search_type = "hybrid"

        # Execute unified search
        results = await unified_service.search(
            query=query,
            limit=limit,
            search_type=actual_search_type,
            filters=filters,
            user_context=user_context,
        )

        if results:
            return results

        # Fallback to database if no results
        if search_type == "auto":
            logger.info("No results from unified search, trying database fallback")
            return await search_database(query, limit, tags, None, current_user, tenant_id)

        return []

    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        # Fallback to database on any error
        try:
            return await search_database(query, limit, tags, None, current_user, tenant_id)
        except Exception:
            return []


@router.get("/analytics", response_model=dict)
async def get_search_analytics(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get comprehensive search and document analytics from Elasticsearch
    """
    try:
        search_service = SearchService(tenant_id)
        analytics = await search_service.get_search_analytics(date_from, date_to)
        return {
            "success": True,
            "analytics": analytics
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "analytics": {}
        }


@router.get("/suggest-type", response_model=dict)
async def suggest_search_type(
    query: str = Query(..., description="Query to analyze"),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Suggest optimal search type based on query characteristics
    """
    try:
        search_service = SearchService(tenant_id)
        suggested_type = await search_service.suggest_search_type(query)
        return {
            "success": True,
            "query": query,
            "suggested_type": suggested_type,
            "description": {
                "semantic": "Fast semantic search using Weaviate",
                "hybrid": "Keyword + semantic search using Elasticsearch", 
                "keyword": "Traditional keyword search using Elasticsearch"
            }.get(suggested_type)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "suggested_type": "semantic"  # Safe default
        }


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
    # Use weaviate_client to check health
    health_info = await weaviate_client.health_check()

    return health_info


@router.post("/fix-embedding-model", response_model=dict)
async def fix_embedding_model(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Endpoint removido - el modelo de embeddings ahora es manejado por el microservicio de Weaviate.
    """
    raise HTTPException(
        status_code=501,
        detail="Embedding model management is now handled by the Weaviate microservice"
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
    reindex_service = ReindexService(tenant_id=tenant_id, user_id=str(current_user.id))
    result = await reindex_service.reindex_all_missing()
    return result


@router.post("/reindex/force", response_model=dict)
async def force_reindex_all_documents(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Fuerza el reindexado de TODOS los documentos del tenant.
    ADVERTENCIA: Esta operación puede tomar mucho tiempo.
    """
    # Esta operación es pesada, la ejecutamos en background
    background_tasks.add_task(
        reindex_all_documents_background,
        tenant_id=tenant_id,
        force=True
    )
    
    return {
        "message": "Reindexing started in background",
        "status": "processing",
        "tenant_id": tenant_id
    }


async def reindex_all_documents_background(tenant_id: str, force: bool = False):
    """Background task to reindex all documents"""
    try:
        reindex_service = ReindexService(tenant_id=tenant_id)
        
        if force:
            # Force reindex all documents
            logger.info(f"Starting forced reindex for tenant {tenant_id}")
            await reindex_service.reindex_all_force()
        else:
            # Regular reindex of missing documents
            await reindex_service.reindex_all_missing()
            
        logger.info(f"Reindexing completed for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Error in background reindexing: {e}")


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
    
    reindex_service = ReindexService(tenant_id=tenant_id, user_id=str(current_user.id))
    result = await reindex_service.reindex_specific_documents(document_ids)
    return result


@router.post("/fix-and-reindex", response_model=dict)
async def fix_collection_and_reindex(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Endpoint removido - los problemas de dimensiones ahora son manejados por el microservicio de Weaviate.
    """
    raise HTTPException(
        status_code=501,
        detail="Collection dimension management is now handled by the Weaviate microservice"
    )


@router.post("/auto-reindex", response_model=dict)
async def auto_reindex_failed_documents(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Automáticamente reindexa documentos que tienen errores de indexación.
    """
    reindex_service = ReindexService(tenant_id=tenant_id, user_id=str(current_user.id))
    result = await reindex_service.auto_reindex_failed_documents()
    return result


@router.post("/auto-reindex/start-global", response_model=dict)
async def start_global_auto_reindex(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_async)
):
    """
    Inicia la tarea automática de reindexado para todos los tenants.
    Solo administradores pueden usar este endpoint.
    """
    # Check if user is admin (you might want to add this check)
    # if not current_user.is_superuser:
    #     raise HTTPException(status_code=403, detail="Only administrators can start global auto-reindex")
    
    from app.tasks.auto_reindex_task import auto_reindex_task
    
    # Start the task in background
    background_tasks.add_task(auto_reindex_task.start_periodic_task)
    
    return {
        "message": "Global auto-reindex task started",
        "status": "started",
        "interval_seconds": auto_reindex_task.run_interval
    }


@router.post("/auto-reindex/run-once", response_model=dict)
async def run_auto_reindex_once(
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Ejecuta una sola vez el auto-reindex para el tenant actual.
    """
    from app.tasks.auto_reindex_task import auto_reindex_task
    
    reindex_service = ReindexService(tenant_id=tenant_id, user_id=str(current_user.id))
    result = await reindex_service.auto_reindex_failed_documents()
    
    return {
        "message": "Auto-reindex completed for current tenant",
        "tenant_id": tenant_id,
        "result": result
    }
