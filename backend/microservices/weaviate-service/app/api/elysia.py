"""Elysia API endpoints for advanced agentic RAG"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
import logging

from app.core.security import verify_api_key
from app.services.elysia_service import elysia_service
from app.schemas.elysia import (
    ElysiaQuery, ElysiaResponse, ToolExecution, DecisionTreeState,
    FeedbackRequest, VisualizationRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/query", response_model=ElysiaResponse)
async def elysia_query(
    query: ElysiaQuery,
    _: bool = Depends(verify_api_key)
):
    """Execute Elysia agentic query with decision trees"""
    try:
        # Enhanced logging for debug mode
        if query.enable_debug:
            logger.info(f"🧠 DEBUG MODE ENABLED for query: {query.query[:100]}...")
            logger.info(f"📊 Debug parameters: tenant_id={query.tenant_id}, session_id={query.session_id}")
        
        response = await elysia_service.execute_query(query)
        
        if query.enable_debug and response.data:
            logger.info(f"🔍 Chain of thought data generated: {len(response.data.get('decision_trace', []))} decision steps")
        
        return response
    except Exception as e:
        logger.error(f"❌ Elysia query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tools/execute", response_model=Dict[str, Any])
async def execute_tool(
    tool_execution: ToolExecution,
    _: bool = Depends(verify_api_key)
):
    """Execute a specific tool through Elysia decision tree"""
    try:
        result = await elysia_service.execute_tool(tool_execution)
        return result
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tools")
async def list_available_tools(_: bool = Depends(verify_api_key)):
    """List all available Elysia tools"""
    try:
        tools = await elysia_service.list_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"❌ Failed to list tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/decision-tree/{session_id}/state", response_model=DecisionTreeState)
async def get_decision_tree_state(
    session_id: str,
    _: bool = Depends(verify_api_key)
):
    """Get current decision tree state for a session"""
    try:
        state = await elysia_service.get_decision_tree_state(session_id)
        return state
    except Exception as e:
        logger.error(f"❌ Failed to get decision tree state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/visualize")
async def create_visualization(
    viz_request: VisualizationRequest,
    _: bool = Depends(verify_api_key)
):
    """Create dynamic visualization based on data type"""
    try:
        visualization = await elysia_service.create_visualization(viz_request)
        return visualization
    except Exception as e:
        logger.error(f"❌ Visualization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def submit_feedback(
    feedback: FeedbackRequest,
    _: bool = Depends(verify_api_key)
):
    """Submit feedback for learning and improvement"""
    try:
        result = await elysia_service.process_feedback(feedback)
        return {"status": "success", "feedback_id": result}
    except Exception as e:
        logger.error(f"❌ Feedback processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/session/{session_id}")
async def get_session_analytics(
    session_id: str,
    _: bool = Depends(verify_api_key)
):
    """Get analytics for a specific Elysia session"""
    try:
        analytics = await elysia_service.get_session_analytics(session_id)
        return analytics
    except Exception as e:
        logger.error(f"❌ Failed to get session analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def elysia_health_check():
    """Elysia service health check"""
    try:
        status = await elysia_service.health_check()
        return status
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@router.post("/migrate-from-qdrant")
async def migrate_from_qdrant(
    source_collection: str,
    target_collection: str,
    tenant_id: str,
    batch_size: int = 100,
    _: bool = Depends(verify_api_key)
):
    """Migrate data from Qdrant to Weaviate (TRANSITION HELPER)"""
    try:
        result = await elysia_service.migrate_from_qdrant(
            source_collection, target_collection, tenant_id, batch_size
        )
        return {
            "status": "success",
            "migrated_documents": result.get("migrated", 0),
            "migration_id": result.get("migration_id"),
            "collection": target_collection
        }
    except Exception as e:
        logger.error(f"❌ Migration from Qdrant failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))