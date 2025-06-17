from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, Any, List
from loguru import logger
import uuid
import time

from app.core.langgraph_manager import LangGraphManager
from app.core.security import validate_service_access, validate_tenant_access
from app.schemas.graph import (
    GraphRunRequest,
    GraphRunResult,
    GraphState,
    GraphStructure,
    GraphStepRequest,
    GraphType
)


router = APIRouter()


@router.post("/run", response_model=GraphRunResult)
async def run_graph(
    request: GraphRunRequest,
    context: dict = Depends(validate_service_access)
):
    """Run a graph to completion"""
    try:
        # Validate tenant access
        tenant_id = validate_tenant_access(request.tenant_id, context)
        
        # Get graph manager
        manager = LangGraphManager()
        
        # Create graph instance
        graph = manager.get_graph(
            request.graph_type.value,
            tenant_id=tenant_id,
            user_id=request.user_id
        )
        
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Execute graph
        start_time = time.time()
        
        try:
            # Configure execution
            config = {
                "configurable": {
                    "thread_id": request.thread_id or run_id,
                    "checkpoint_id": request.checkpoint_id
                },
                "recursion_limit": manager.recursion_limit if hasattr(manager, 'recursion_limit') else 25,
                **request.config
            }
            
            # Run graph
            result = await graph.ainvoke(request.input_data, config)
            
            execution_time = time.time() - start_time
            
            return GraphRunResult(
                run_id=run_id,
                graph_type=request.graph_type,
                status="completed",
                result=result,
                execution_time=execution_time,
                iterations=result.get("_iterations", 1),
                final_state=result,
                thread_id=request.thread_id or run_id,
                checkpoint_id=result.get("_checkpoint_id")
            )
            
        except Exception as e:
            logger.error(f"Graph execution failed: {e}")
            execution_time = time.time() - start_time
            
            return GraphRunResult(
                run_id=run_id,
                graph_type=request.graph_type,
                status="failed",
                error=str(e),
                execution_time=execution_time,
                iterations=0,
                thread_id=request.thread_id or run_id
            )
            
    except Exception as e:
        logger.error(f"Failed to run graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_graph(
    request: GraphRunRequest,
    context: dict = Depends(validate_service_access)
):
    """Stream graph execution results"""
    try:
        # Validate tenant access
        tenant_id = validate_tenant_access(request.tenant_id, context)
        
        # Get graph manager
        manager = LangGraphManager()
        
        # Create graph instance
        graph = manager.get_graph(
            request.graph_type.value,
            tenant_id=tenant_id,
            user_id=request.user_id
        )
        
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Configure execution
        config = {
            "configurable": {
                "thread_id": request.thread_id or run_id,
                "checkpoint_id": request.checkpoint_id
            },
            **request.config
        }
        
        # Stream results
        events = []
        async for event in graph.astream_events(request.input_data, config, version="v1"):
            events.append({
                "event": event["event"],
                "name": event.get("name"),
                "data": event.get("data"),
                "metadata": event.get("metadata")
            })
        
        return {
            "run_id": run_id,
            "events": events,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Failed to stream graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{run_id}", response_model=GraphState)
async def get_graph_state(
    run_id: str,
    context: dict = Depends(validate_service_access)
):
    """Get the current state of a graph execution"""
    try:
        # This would typically fetch from checkpointer
        # For now, return a placeholder
        return GraphState(
            run_id=run_id,
            graph_type=GraphType.TAG_GENERATION,
            state_data={},
            iteration=0,
            status="unknown",
            created_at=time.time(),
            updated_at=time.time()
        )
        
    except Exception as e:
        logger.error(f"Failed to get graph state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/step")
async def step_graph(
    request: GraphStepRequest,
    context: dict = Depends(validate_service_access)
):
    """Execute a single step in a graph"""
    try:
        # This would handle step-by-step execution
        # For now, return a placeholder
        return {
            "run_id": request.run_id,
            "status": "step_completed",
            "next_node": "unknown"
        }
        
    except Exception as e:
        logger.error(f"Failed to step graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types", response_model=List[str])
async def list_graph_types(
    context: dict = Depends(validate_service_access)
):
    """List available graph types"""
    try:
        manager = LangGraphManager()
        return list(manager.graphs.keys())
        
    except Exception as e:
        logger.error(f"Failed to list graph types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/structure/{graph_type}", response_model=GraphStructure)
async def get_graph_structure(
    graph_type: GraphType,
    context: dict = Depends(validate_service_access)
):
    """Get the structure of a specific graph type"""
    try:
        manager = LangGraphManager()
        graph_class = manager.graphs.get(graph_type.value)
        
        if not graph_class:
            raise HTTPException(status_code=404, detail=f"Graph type not found: {graph_type}")
        
        # Get graph structure from class
        structure = graph_class.get_structure()
        
        return GraphStructure(
            graph_type=graph_type,
            nodes=structure["nodes"],
            edges=structure["edges"],
            entry_point=structure["entry_point"],
            description=structure.get("description")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get graph structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkpoint/save")
async def save_checkpoint(
    run_id: str,
    context: dict = Depends(validate_service_access)
):
    """Save a checkpoint for a graph execution"""
    try:
        # This would save checkpoint
        return {
            "run_id": run_id,
            "checkpoint_id": str(uuid.uuid4()),
            "status": "saved"
        }
        
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkpoint/{checkpoint_id}/resume")
async def resume_from_checkpoint(
    checkpoint_id: str,
    input_data: Dict[str, Any],
    context: dict = Depends(validate_service_access)
):
    """Resume graph execution from a checkpoint"""
    try:
        # This would resume from checkpoint
        return {
            "checkpoint_id": checkpoint_id,
            "status": "resumed",
            "run_id": str(uuid.uuid4())
        }
        
    except Exception as e:
        logger.error(f"Failed to resume from checkpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))