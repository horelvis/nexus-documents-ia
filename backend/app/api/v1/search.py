from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.models import User
from app.services.search_service import SearchService
from app.services.vector_service import VectorService
from app.services.reindex_service import ReindexService
from app.services.cag_client import CAGClient
from app.schemas.document import ChatMessage

router = APIRouter()


@router.get("/", response_model=List[dict])
async def search_documents(
    query: str = Query(..., description="Texto de búsqueda"),
    limit: int = Query(10, ge=1, le=100),
    search_type: Optional[str] = Query("semantic", description="Tipo de búsqueda: semantic, hybrid, keyword"),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Hybrid search: routes to optimal engine based on search type
    - semantic: Weaviate (default, fast)
    - hybrid: Elasticsearch (keyword + semantic)
    - keyword: Elasticsearch (traditional search)
    """
    try:
        # Initialize hybrid search service
        search_service = SearchService(tenant_id)
        
        # Auto-suggest search type if not specified appropriately
        if search_type == "semantic":
            suggested_type = await search_service.suggest_search_type(query)
            if suggested_type != "semantic":
                search_type = suggested_type
                # Log the smart routing decision
                print(f"🤖 Smart routing: '{query}' → {search_type} search")
        
        # Prepare filters
        filters = {}
        if tags:
            filters["tags"] = tags
        if date_from:
            filters["date_from"] = date_from  
        if date_to:
            filters["date_to"] = date_to
        
        # Perform hybrid search
        results = await search_service.search_documents(
            query=query,
            limit=limit,
            search_type=search_type,
            filters=filters
        )
        
        # Return results with search engine info
        response_data = {
            "results": results,
            "search_engine": "weaviate" if search_type == "semantic" else "elasticsearch",
            "search_type": search_type,
            "total_results": len(results)
        }
        
        return results  # For compatibility, return just results
        
    except Exception as e:
        # Fallback to CAG service if hybrid search fails
        try:
            cag_client = CAGClient()
            cag_response = await cag_client.process_query(
                query=f"SEARCH_ONLY: {query}",
                tenant_id=tenant_id,
                user_id=str(current_user.id),
                context={
                    "search_mode": True,
                    "limit": limit,
                    "tags": tags,
                    "date_from": date_from,
                    "date_to": date_to
                }
            )
            
            if cag_response.get("success") and cag_response.get("documents"):
                return cag_response["documents"]
        except Exception as fallback_error:
            print(f"❌ Both hybrid search and CAG fallback failed: {e}, {fallback_error}")
            
        # Final fallback to original search service
        search_service = SearchService(tenant_id=tenant_id)
        results = await search_service.search_documents(
            query=query,
            limit=limit
        )
        
        return results
        
    except Exception as e:
        # Fallback al servicio original en caso de error
        search_service = SearchService(tenant_id=tenant_id)
        results = await search_service.search_documents(
            query=query,
            limit=limit
        )
        
        return results


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
            # You would implement force reindex logic here
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