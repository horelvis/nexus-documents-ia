"""Migration API endpoints for gradual Qdrant->Weaviate transition"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging

from app.api.dependencies import get_current_tenant
from app.services.migration_service import migration_service
from app.db.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/status")
async def get_migration_status():
    """Get current migration status and configuration"""
    try:
        status = migration_service.get_migration_status()
        return status
    except Exception as e:
        logger.error(f"❌ Failed to get migration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def get_migration_health():
    """Check health of migration service and underlying systems"""
    try:
        health = await migration_service.health_check()
        return health
    except Exception as e:
        logger.error(f"❌ Migration health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search")
async def search_documents_migrated(
    query: str,
    limit: int = Query(default=10, ge=1, le=100),
    query_type: str = Query(default="search", regex="^(search|analyze|extract|summarize|compare)$"),
    collections: Optional[List[str]] = Query(default=None),
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Search documents using current migration strategy"""
    try:
        search_kwargs = {
            "limit": limit,
            "query_type": query_type,
            "collections": collections or []
        }
        
        result = await migration_service.search_documents(
            query=query,
            tenant_id=str(current_tenant.id),
            **search_kwargs
        )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Migration search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents")
async def add_document_migrated(
    document_data: Dict[str, Any],
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Add document using current migration strategy"""
    try:
        # Ensure tenant_id is set
        document_data["tenant_id"] = str(current_tenant.id)
        
        result = await migration_service.add_document(document_data)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Migration document add failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start-migration")
async def start_migration(
    source_collection: str = Query(..., description="Source Qdrant collection name"),
    target_collection: Optional[str] = Query(None, description="Target Weaviate collection name"),
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Start migration from Qdrant to Weaviate for current tenant"""
    try:
        # Generate target collection name if not provided
        if not target_collection:
            target_collection = f"nexus_{str(current_tenant.id)}_documents".lower().replace("-", "_")
        
        result = await migration_service.start_migration(
            source_collection=source_collection,
            target_collection=target_collection,
            tenant_id=str(current_tenant.id)
        )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Migration start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/compare")
async def compare_systems(
    query: str,
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Compare results between Qdrant and Weaviate systems"""
    try:
        logger.info(f"🔍 Comparing systems for query: {query}")
        
        # Force parallel mode for comparison
        original_mode = migration_service.migration_mode
        migration_service.migration_mode = migration_service.MigrationMode.PARALLEL
        
        try:
            result = await migration_service.search_documents(
                query=query,
                tenant_id=str(current_tenant.id),
                limit=10
            )
            
            # Extract comparison data
            comparison = {
                "query": query,
                "timestamp": result.get("timestamp"),
                "systems": result.get("systems", {}),
                "analysis": {}
            }
            
            # Analyze results
            qdrant_results = result.get("systems", {}).get("qdrant", {}).get("results", {})
            weaviate_results = result.get("systems", {}).get("weaviate", {}).get("results", {})
            
            comparison["analysis"] = {
                "qdrant_result_count": len(qdrant_results.get("results", [])) if isinstance(qdrant_results, dict) else 0,
                "weaviate_result_count": len(weaviate_results.get("results", [])) if isinstance(weaviate_results, dict) else 0,
                "both_succeeded": "qdrant" in result.get("systems", {}) and "weaviate" in result.get("systems", {}),
                "performance_comparison": {
                    "qdrant_time": qdrant_results.get("search_time_ms") if isinstance(qdrant_results, dict) else None,
                    "weaviate_time": weaviate_results.get("execution_time_ms") if isinstance(weaviate_results, dict) else None
                }
            }
            
            return comparison
            
        finally:
            # Restore original mode
            migration_service.migration_mode = original_mode
        
    except Exception as e:
        logger.error(f"❌ System comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tools")
async def list_available_tools():
    """List tools available in Weaviate/Elysia system"""
    try:
        if not migration_service.enable_weaviate:
            return {"tools": [], "message": "Weaviate system not enabled"}
        
        from app.services.weaviate_client import weaviate_client
        tools = await weaviate_client.list_tools()
        
        return {
            "tools": tools,
            "count": len(tools),
            "system": "weaviate_elysia"
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to list tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def submit_feedback(
    feedback_data: Dict[str, Any],
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Submit feedback for learning (Weaviate/Elysia only)"""
    try:
        if not migration_service.enable_weaviate:
            raise HTTPException(
                status_code=400, 
                detail="Feedback requires Weaviate system to be enabled"
            )
        
        feedback_data["tenant_id"] = str(current_tenant.id)
        
        from app.services.weaviate_client import weaviate_client
        result = await weaviate_client.submit_feedback(feedback_data)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Feedback submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/visualize") 
async def create_visualization(
    visualization_data: Dict[str, Any],
    current_tenant: Tenant = Depends(get_current_tenant)
):
    """Create dynamic visualization (Weaviate/Elysia only)"""
    try:
        if not migration_service.enable_weaviate:
            raise HTTPException(
                status_code=400,
                detail="Visualization requires Weaviate system to be enabled"
            )
        
        visualization_data["tenant_id"] = str(current_tenant.id)
        
        from app.services.weaviate_client import weaviate_client
        result = await weaviate_client.create_visualization(visualization_data)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Visualization creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))