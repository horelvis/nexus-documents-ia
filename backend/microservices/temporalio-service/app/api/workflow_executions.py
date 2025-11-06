"""Workflow Executions Management API"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
import uuid

from temporalio.client import WorkflowHandle
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.core.config import settings
from app.core.temporalio_client import temporalio_client
from app.workflows.dynamic_workflow import DynamicWorkflow, DynamicWorkflowInput

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)


# Pydantic Models
class WorkflowExecutionRequest(BaseModel):
    template_id: str = Field(..., description="Template ID to execute")
    input_data: Dict[str, Any] = Field(..., description="Workflow input data")
    tenant_id: str = Field(..., description="Tenant ID")
    workflow_id: Optional[str] = Field(None, description="Custom workflow ID")
    task_queue: Optional[str] = Field(None, description="Custom task queue")


class WorkflowExecutionResponse(BaseModel):
    success: bool
    workflow_id: str
    template_id: str
    status: str
    message: str
    started_at: str


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    template_id: str
    tenant_id: str
    status: str  # "running", "completed", "failed", "cancelled"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


@router.post("/start", response_model=WorkflowExecutionResponse)
async def start_workflow_execution(request: WorkflowExecutionRequest):
    """Start a new workflow execution from a template"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Generate workflow ID if not provided
        workflow_id = request.workflow_id or f"{request.template_id}-{uuid.uuid4().hex[:8]}"
        
        # Get template definition
        from app.data.workflow_templates_ai import get_all_ai_enhanced_templates
        
        template_definition = None
        ai_templates = get_all_ai_enhanced_templates()
        
        # Find the template
        for template in ai_templates:
            if template["id"] == request.template_id:
                template_definition = template
                break
        
        # Fallback to legacy template if not found in AI templates
        if not template_definition and request.template_id == "legal-advisory-template":
            template_definition = {
                "id": "legal-advisory-template",
                "name": "Asesoría Legal (Legacy)",
                "workflow_definition": {
                    "start_step": "intake",
                    "steps": [
                        {
                            "step_id": "intake",
                            "step_name": "Recopilación de Información",
                            "step_type": "activity",
                            "activity_type": "emma_ai_legal_analysis",
                            "activity_config": {},
                            "next_steps": {"success": "end"}
                        }
                    ]
                }
            }
        
        if not template_definition:
            raise HTTPException(status_code=404, detail=f"Template {request.template_id} not found")
        
        # Prepare workflow input with correct field names
        workflow_input = DynamicWorkflowInput(
            template_id=request.template_id,
            template_name=template_definition.get("name", "Unknown Template"),
            template_version=template_definition.get("version", "1.0"),
            tenant_id=request.tenant_id,
            user_id="test-user",  # TODO: Get from auth context
            execution_id=workflow_id,
            workflow_definition=template_definition["workflow_definition"],
            user_input_data=request.input_data,  # Correct field name
            context={}
        )

        # Start the workflow
        task_queue = request.task_queue or settings.temporalio_task_queue
        
        handle = await temporalio_client.client.start_workflow(
            DynamicWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=task_queue,
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=3
            )
        )

        logger.info(f"Started workflow {workflow_id} from template {request.template_id}")
        
        return WorkflowExecutionResponse(
            success=True,
            workflow_id=workflow_id,
            template_id=request.template_id,
            status="running",
            message=f"Workflow {workflow_id} started successfully",
            started_at=datetime.now().isoformat()
        )

    except WorkflowAlreadyStartedError:
        raise HTTPException(status_code=409, detail=f"Workflow with ID {workflow_id} already exists")
    except Exception as e:
        logger.error(f"Error starting workflow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """Get the status of a workflow execution"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # Check if workflow exists and get its status
        try:
            describe = await handle.describe()
            
            # Determine status
            if describe.status.name == "RUNNING":
                status = "running"
                result = None
                error = None
                completed_at = None
            elif describe.status.name == "COMPLETED":
                status = "completed"
                try:
                    result = await handle.result()
                    if hasattr(result, 'dict'):
                        result = result.dict()
                    elif hasattr(result, '__dict__'):
                        result = result.__dict__
                except:
                    result = {"message": "Workflow completed successfully"}
                error = None
                completed_at = describe.close_time.isoformat() if describe.close_time else None
            elif describe.status.name == "FAILED":
                status = "failed"
                result = None
                error = "Workflow execution failed"
                completed_at = describe.close_time.isoformat() if describe.close_time else None
            elif describe.status.name == "CANCELLED":
                status = "cancelled"
                result = None
                error = "Workflow was cancelled"
                completed_at = describe.close_time.isoformat() if describe.close_time else None
            else:
                status = describe.status.name.lower()
                result = None
                error = None
                completed_at = None

            return WorkflowStatusResponse(
                workflow_id=workflow_id,
                template_id="unknown",  # TODO: Extract from workflow metadata
                tenant_id="unknown",  # TODO: Extract from workflow metadata
                status=status,
                result=result,
                error=error,
                created_at=describe.start_time.isoformat() if describe.start_time else datetime.now().isoformat(),
                completed_at=completed_at,
                progress=None  # TODO: Implement progress tracking
            )

        except Exception as e:
            # Workflow might not exist
            logger.warning(f"Workflow {workflow_id} not found or error getting status: {e}")
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow status for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


@router.post("/{workflow_id}/cancel")
async def cancel_workflow_execution(workflow_id: str):
    """Cancel a running workflow execution"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Get workflow handle and cancel
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        await handle.cancel()
        
        logger.info(f"Cancelled workflow {workflow_id}")
        return {"message": f"Workflow {workflow_id} cancelled successfully"}

    except Exception as e:
        logger.error(f"Error cancelling workflow {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel workflow: {str(e)}")


@router.get("/", response_model=List[WorkflowStatusResponse])
async def list_workflow_executions(
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List workflow executions with optional filtering"""
    try:
        # TODO: Implement actual workflow listing from Temporalio
        # This would require querying Temporalio's visibility APIs
        # For now, return empty list
        logger.info(f"Listing workflows for tenant {tenant_id} with status {status}")
        return []

    except Exception as e:
        logger.error(f"Error listing workflow executions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list workflow executions: {str(e)}")


@router.get("/{workflow_id}/history")
async def get_workflow_history(workflow_id: str):
    """Get the execution history of a workflow"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # TODO: Implement history retrieval
        # This would require accessing Temporalio's history APIs
        logger.info(f"Getting history for workflow {workflow_id}")
        
        return {
            "workflow_id": workflow_id,
            "history": [],
            "message": "History retrieval not yet implemented"
        }

    except Exception as e:
        logger.error(f"Error getting workflow history for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow history: {str(e)}")